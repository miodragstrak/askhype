#!/usr/bin/env python3
"""LOCAL/QA only: seek animated SVGs in Chromium and compose an MP4 with FFmpeg."""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.renderers.svg_sanitizer import MAX_SVG_BYTES, SvgValidationError, sanitize_svg
from app.schemas.generative_svg import StoryboardPlan
from pydantic import ValidationError

WIDTH, HEIGHT, DEFAULT_FPS = 1280, 720, 25
TRANSITION_SECONDS = 0.6
CAPTURE_TIMEOUT_SECONDS, ENCODE_TIMEOUT_SECONDS = 600, 180
TRANSITIONS = {"fade": "fadeblack", "crossfade": "fade", "slide": "slideleft"}


class ExportError(RuntimeError):
    pass


def load_storyboard(directory: Path) -> tuple[StoryboardPlan, list[str]]:
    """Validate existing files without executing their code or fetching resources."""
    manifest = directory / "storyboard.json"
    if manifest.stat().st_size > 250_000:
        raise ExportError("storyboard.json exceeds 250 KB.")
    try:
        plan = StoryboardPlan.model_validate_json(manifest.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise ExportError(f"Invalid storyboard.json: {exc}") from exc
    if len({scene.id for scene in plan.scenes}) != len(plan.scenes):
        raise ExportError("Storyboard scene IDs must be unique.")
    sources = []
    for index, scene in enumerate(plan.scenes, 1):
        source = directory / f"scene-{index:02d}.svg"
        if source.resolve().parent != directory.resolve():
            raise ExportError(f"{source.name} must stay inside the input directory.")
        if source.stat().st_size > MAX_SVG_BYTES:
            raise ExportError(f"{source.name} exceeds the SVG size limit.")
        try:
            sources.append(sanitize_svg(
                source.read_text(encoding="utf-8"), duration_seconds=scene.duration_seconds,
            ).content)
        except SvgValidationError as exc:
            raise ExportError(f"Unsafe or invalid {source.name}: {exc}") from exc
    return plan, sources


def transition_frames(fps: int) -> int:
    return max(1, round(TRANSITION_SECONDS * fps))


def scene_frame_counts(plan: StoryboardPlan, fps: int) -> list[int]:
    # Each outgoing scene has a live animation handle for the next scene's
    # opening transition. xfade consumes these handles, preserving the total.
    handle = transition_frames(fps)
    return [scene.duration_seconds * fps + (handle if i < len(plan.scenes) - 1 else 0)
            for i, scene in enumerate(plan.scenes)]


def write_capture_page(workspace: Path, sources: list[str]) -> Path:
    # Each SVG has its own document: repeated gradient IDs and CSS/keyframe names
    # must never leak into another scene. Scripts and external resources are off.
    inner_style = "html,body{margin:0;width:100%;height:100%;overflow:hidden;background:black}"
    frames = []
    for source in sources:
        content = f"<!doctype html><html><head><style>{inner_style}</style></head><body>{source}</body></html>"
        frames.append(f'<iframe sandbox="allow-same-origin" srcdoc="{html.escape(content, quote=True)}"></iframe>')
    page = workspace / "capture.html"
    page.write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; frame-src \'self\' about:">'
        f"<style>{inner_style}iframe{{position:absolute;inset:0;width:{WIDTH}px;height:{HEIGHT}px;"
        'border:0;visibility:hidden}</style></head><body>' + "".join(frames) + "</body></html>",
        encoding="utf-8",
    )
    return page


class ChromeSession:
    """Small synchronous CDP client; one private browser/profile per export."""

    def __init__(self, socket: Any):
        self.socket = socket
        self.sequence = 0
        self.session_id: str | None = None

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sequence += 1
        message: dict[str, Any] = {"id": self.sequence, "method": method, "params": params or {}}
        if self.session_id:
            message["sessionId"] = self.session_id
        self.socket.send(json.dumps(message))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = json.loads(self.socket.recv(timeout=max(0.01, deadline - time.monotonic())))
            if response.get("id") == self.sequence:
                if "error" in response:
                    raise ExportError(f"Chromium {method} failed: {response['error']}")
                return response.get("result", {})
        raise ExportError(f"Chromium {method} timed out.")

    def evaluate(self, expression: str) -> Any:
        result = self.call("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True,
        })
        if "exceptionDetails" in result:
            raise ExportError(f"Chromium animation seek failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")


def find_chrome() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable"):
        if executable := shutil.which(name):
            return executable
    raise ExportError("Local Google Chrome/Chromium is required for animated SVG capture.")


@contextmanager
def open_chrome(workspace: Path, executable: str) -> Iterator[ChromeSession]:
    try:
        from websockets.exceptions import WebSocketException
        from websockets.sync.client import connect
    except ImportError as exc:
        raise ExportError("Install local QA dependencies with: pip install -e '.[dev]'") from exc
    profile = workspace / "chrome-profile"
    log_path = workspace / "chrome.log"
    command = [
        executable, "--headless=new", "--disable-gpu", "--disable-background-networking",
        "--disable-component-update", "--disable-sync", "--metrics-recording-only",
        "--no-first-run", "--no-default-browser-check", "--no-proxy-server",
        "--host-resolver-rules=MAP * ~NOTFOUND", "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0", f"--user-data-dir={profile}",
        f"--window-size={WIDTH},{HEIGHT}", "--force-device-scale-factor=1", "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw", "about:blank",
    ]
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        try:
            port_file = profile / "DevToolsActivePort"
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise ExportError(f"Chromium exited at startup: {log_path.read_text(errors='replace')[-1200:]}")
                try:
                    lines = port_file.read_text().splitlines()
                    if len(lines) >= 2:
                        break
                except FileNotFoundError:
                    pass
                if time.monotonic() >= deadline:
                    raise ExportError("Chromium startup timed out.")
                time.sleep(0.05)
            with connect(f"ws://127.0.0.1:{int(lines[0])}{lines[1]}", open_timeout=10,
                         close_timeout=2, max_size=16_000_000, compression=None) as socket:
                chrome = ChromeSession(socket)
                target = chrome.call("Target.createTarget", {"url": "about:blank"})
                attached = chrome.call("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})
                chrome.session_id = attached["sessionId"]
                chrome.call("Page.enable")
                chrome.call("Emulation.setDeviceMetricsOverride", {
                    "width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1, "mobile": False,
                })
                yield chrome
        except WebSocketException as exc:
            raise ExportError(f"Chromium DevTools connection failed: {exc}") from exc
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def capture_scenes(chrome: ChromeSession, workspace: Path, page: Path,
                   plan: StoryboardPlan, fps: int) -> list[dict[str, Any]]:
    chrome.call("Page.navigate", {"url": page.as_uri()})
    deadline = time.monotonic() + 20
    while not chrome.evaluate(
        "document.readyState === 'complete' && "
        f"document.querySelectorAll('iframe').length === {len(plan.scenes)} && "
        "[...document.querySelectorAll('iframe')].every(f => f.contentDocument?.readyState === 'complete')"
    ):
        if time.monotonic() >= deadline:
            raise ExportError("SVG scene documents did not load in Chromium.")
        time.sleep(0.05)
    animation_counts = chrome.evaluate("""(async () => {
        window.exportScenes = [...document.querySelectorAll('iframe')].map(frame => ({
            frame, animations: frame.contentDocument.getAnimations()
        }));
        for (const scene of window.exportScenes) {
            await Promise.all(scene.animations.map(animation => {
                animation.pause(); return animation.ready;
            }));
            for (const animation of scene.animations) animation.currentTime = 0;
        }
        return window.exportScenes.map(scene => scene.animations.length);
    })()""")
    counts = scene_frame_counts(plan, fps)
    started = time.monotonic()
    metrics = []
    for scene_index, (scene, count) in enumerate(zip(plan.scenes, counts)):
        directory = workspace / f"scene-{scene_index + 1:02d}"
        directory.mkdir()
        print(f"Capturing {scene.id}: {count} frames at {fps} fps "
              f"({animation_counts[scene_index]} CSS animations)", file=sys.stderr, flush=True)
        for frame in range(count):
            if time.monotonic() - started > CAPTURE_TIMEOUT_SECONDS:
                raise ExportError("Storyboard capture exceeded the 10-minute local QA limit.")
            # Web Animations currentTime preserves authored delays, direction,
            # easing, fill mode and iterations, independent of wall-clock speed.
            chrome.evaluate(f"""(() => {{
                const selected = window.exportScenes[{scene_index}];
                for (const scene of window.exportScenes)
                    scene.frame.style.visibility = scene === selected ? 'visible' : 'hidden';
                for (const animation of selected.animations) animation.currentTime = {frame * 1000 / fps!r};
                selected.frame.contentDocument.documentElement.getBoundingClientRect();
            }})()""")
            screenshot = chrome.call("Page.captureScreenshot", {
                "format": "png", "fromSurface": True, "captureBeyondViewport": False,
                "clip": {"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT, "scale": 1},
            })
            (directory / f"frame-{frame:06d}.png").write_bytes(base64.b64decode(screenshot["data"]))
        metrics.append({"id": scene.id, "duration_seconds": scene.duration_seconds,
                        "captured_frames": count, "css_animations": animation_counts[scene_index]})
    return metrics


def composition_filter(plan: StoryboardPlan, fps: int) -> str:
    duration = transition_frames(fps) / fps
    filters = [f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS,format=yuv444p[s{i}]"
               for i in range(len(plan.scenes))]
    black = f"color=c=black:s={WIDTH}x{HEIGHT}:r={fps}:d={duration:g},format=yuv444p,settb=AVTB"
    # At a shared boundary transition_in is authoritative; transition_out on
    # the final scene closes the film. This also handles disagreeing metadata.
    filters += [f"{black}[intro]",
                f"[intro][s0]xfade=transition={TRANSITIONS[plan.scenes[0].transition_in]}:"
                f"duration={duration:g}:offset=0[v0]"]
    offset = 0
    for i in range(1, len(plan.scenes)):
        offset += plan.scenes[i - 1].duration_seconds
        filters.append(f"[v{i - 1}][s{i}]xfade=transition={TRANSITIONS[plan.scenes[i].transition_in]}:"
                       f"duration={duration:g}:offset={offset:g}[v{i}]")
    filters += [f"{black}[outro]",
                f"[v{len(plan.scenes) - 1}][outro]xfade=transition={TRANSITIONS[plan.scenes[-1].transition_out]}:"
                f"duration={duration:g}:offset={plan.total_duration_seconds - duration:g},"
                f"trim=duration={plan.total_duration_seconds},setpts=PTS-STARTPTS,format=yuv420p[video]"]
    return ";".join(filters)


def ffmpeg_command(executable: str, workspace: Path, output: Path,
                   plan: StoryboardPlan, fps: int) -> list[str]:
    command = [executable, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "2"]
    for index in range(len(plan.scenes)):
        command += ["-framerate", str(fps), "-start_number", "0", "-i",
                    str(workspace / f"scene-{index + 1:02d}" / "frame-%06d.png")]
    return command + [
        "-filter_complex", composition_filter(plan, fps), "-map", "[video]", "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-threads", "2",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-fps_mode", "cfr",
        "-frames:v", str(plan.total_duration_seconds * fps), "-t", str(plan.total_duration_seconds),
        "-movflags", "+faststart", "-f", "mp4", str(output),
    ]


def inspect_video(output: Path, plan: StoryboardPlan, fps: int) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {"validation": "ffprobe unavailable; media properties were not independently verified",
                "file_size_bytes": output.stat().st_size}
    result = subprocess.run([
        executable, "-v", "error", "-show_entries",
        "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames:format=duration,size",
        "-of", "json", str(output),
    ], capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise ExportError(f"ffprobe failed: {result.stderr[-1200:]}")
    try:
        data = json.loads(result.stdout)
        streams = data["streams"]
        video, = [stream for stream in streams if stream["codec_type"] == "video"]
        metrics = {
            "duration_seconds": float(data["format"]["duration"]),
            "width": int(video["width"]), "height": int(video["height"]),
            "fps": float(Fraction(video["avg_frame_rate"])), "codec": video["codec_name"],
            "pixel_format": video["pix_fmt"], "file_size_bytes": int(data["format"]["size"]),
        }
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        raise ExportError("ffprobe returned incomplete or invalid media properties.") from exc
    if ((metrics["width"], metrics["height"]) != (WIDTH, HEIGHT)
            or metrics["codec"] != "h264" or metrics["pixel_format"] != "yuv420p"
            or not math.isclose(metrics["fps"], fps, abs_tol=0.001)
            or abs(metrics["duration_seconds"] - plan.total_duration_seconds) > 1 / fps + 0.001
            or len(streams) != 1
            or ("nb_frames" in video and int(video["nb_frames"]) != plan.total_duration_seconds * fps)):
        raise ExportError(f"MP4 failed output validation: {metrics}")
    return {"validation": "passed", **metrics}


def export_storyboard(directory: Path, output: Path | None = None, fps: int = DEFAULT_FPS) -> dict[str, Any]:
    if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 60:
        raise ExportError("FPS must be an integer between 1 and 60.")
    started = time.monotonic()
    directory = directory.resolve()
    output = (output or directory / "final-video.mp4").absolute()
    if output.suffix.lower() != ".mp4":
        raise ExportError("Output must use the .mp4 extension.")
    plan, sources = load_storyboard(directory)
    chrome_executable = find_chrome()
    ffmpeg_executable = shutil.which("ffmpeg")
    if not ffmpeg_executable:
        raise ExportError("Local FFmpeg with the libx264 encoder is required.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage beside the destination for atomic replacement on the same filesystem.
    # TemporaryDirectory removes frames/profile/partial MP4 on failure or Ctrl-C.
    with tempfile.TemporaryDirectory(prefix="askhype-storyboard-", dir=output.parent) as temporary:
        workspace = Path(temporary)
        page = write_capture_page(workspace, sources)
        capture_started = time.monotonic()
        with open_chrome(workspace, chrome_executable) as chrome:
            scenes = capture_scenes(chrome, workspace, page, plan, fps)
        capture_seconds = time.monotonic() - capture_started
        staged_output = workspace / "final-video.mp4"
        print("Composing transitions and encoding MP4 with FFmpeg", file=sys.stderr, flush=True)
        result = subprocess.run(ffmpeg_command(ffmpeg_executable, workspace, staged_output, plan, fps),
                                capture_output=True, text=True, timeout=ENCODE_TIMEOUT_SECONDS, check=False)
        if result.returncode or not staged_output.is_file() or not staged_output.stat().st_size:
            raise ExportError(f"FFmpeg could not compose the MP4: {result.stderr[-1200:]}")
        metrics = inspect_video(staged_output, plan, fps)
        staged_output.replace(output)
    return {
        "output": str(output), "input": str(directory), "scene_count": len(plan.scenes),
        "storyboard_duration_seconds": plan.total_duration_seconds,
        "output_frames": plan.total_duration_seconds * fps,
        "capture_seconds": round(capture_seconds, 3), "export_seconds": round(time.monotonic() - started, 3),
        "transition_seconds": transition_frames(fps) / fps,
        "transitions": [scene.transition_in for scene in plan.scenes] + [plan.scenes[-1].transition_out],
        "scenes": scenes, **metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Completed storyboard output directory")
    parser.add_argument("--output", type=Path, help="MP4 destination (default: INPUT/final-video.mp4)")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Output/capture frame rate (default: 25)")
    args = parser.parse_args()
    try:
        report = export_storyboard(args.input, args.output, args.fps)
    except (ExportError, OSError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
        print(f"Storyboard export failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Storyboard export cancelled; temporary files removed.", file=sys.stderr)
        return 130
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
