"""Local exporter validation plus an opt-in real Chromium/FFmpeg regression."""

import base64
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from scripts import export_storyboard_video as exporter


def write_storyboard(directory: Path):
    shared = dict.fromkeys([
        "title", "scene_description", "background_description", "composition", "visual_style",
        "shape_language", "lighting", "line_treatment", "depth_style", "mood", "motion_style",
    ], "Local export test")
    shared.update(duration_seconds=10, palette=["#000000", "#ffffff"],
                  timeline_beats=[{"start": 0, "duration": 10, "description": "Move", "motion": "Glide"}])
    data = {
        "title": "Export regression", "total_duration_seconds": 10, "shared_art_direction": shared,
        "scenes": [
            {"id": f"scene_{i + 1}", "duration_seconds": duration,
             "description": "Moving circle", "environment": "Color", "action": "Glide",
             "mood": "Calm", "composition": "Wide", "transition_in": transition_in,
             "transition_out": transition_out}
            for i, (duration, transition_in, transition_out) in enumerate([
                (2, "fade", "crossfade"), (2, "crossfade", "slide"), (6, "slide", "fade"),
            ])
        ],
    }
    (directory / "storyboard.json").write_text(json.dumps(data), encoding="utf-8")
    for index, color in enumerate(["#ff0000", "#00ff00", "#0000ff"], 1):
        # Reused IDs/CSS across scenes deliberately exercise document isolation.
        (directory / f"scene-{index:02d}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
            '<style>@keyframes travel{0%{transform:translateX(0)}100%{transform:translateX(400px)}}'
            '.moving{animation:travel 2s linear 0.2s infinite alternate-reverse}</style>'
            f'<rect width="1280" height="720" fill="{color}"/>'
            '<circle id="hero" class="moving" cx="100" cy="360" r="40" fill="#ffffff"/></svg>',
            encoding="utf-8",
        )
    return data


def test_live_handles_and_fixed_composition_preserve_every_scene_duration(tmp_path):
    write_storyboard(tmp_path)
    plan, _ = exporter.load_storyboard(tmp_path)
    counts = exporter.scene_frame_counts(plan, 25)
    assert counts == [65, 65, 150]
    # Removing exactly the two overlaps leaves the full 250-frame storyboard.
    assert sum(counts) - 2 * exporter.transition_frames(25) == 250
    filters = exporter.composition_filter(plan, 25)
    assert "transition=fade:duration=0.6:offset=2" in filters
    assert "transition=slideleft:duration=0.6:offset=4" in filters
    assert "offset=9.4" in filters
    assert "trim=duration=10" in filters
    command = exporter.ffmpeg_command("/usr/bin/ffmpeg", tmp_path, tmp_path / "a;$(echo unsafe).mp4", plan, 25)
    assert command[-1] == str(tmp_path / "a;$(echo unsafe).mp4")
    assert command[command.index("-frames:v") + 1] == "250"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "-an" in command


@pytest.mark.parametrize("change", ["duration", "transition", "duplicate", "missing", "script", "external", "symlink"])
def test_bad_inputs_rejected_before_browser_start(tmp_path, change):
    data = write_storyboard(tmp_path)
    if change == "duration":
        data["total_duration_seconds"] = 11
    elif change == "transition":
        data["scenes"][1]["transition_in"] = "fade;movie=/etc/passwd"
    elif change == "duplicate":
        data["scenes"][1]["id"] = "scene_1"
    elif change == "missing":
        (tmp_path / "scene-02.svg").unlink()
    elif change in {"script", "external"}:
        (tmp_path / "scene-02.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">' +
            ('<script>alert(1)</script>' if change == "script" else '<image href="file:///etc/passwd"/>') + '</svg>',
        )
    elif change == "symlink":
        (tmp_path / "scene-02.svg").unlink()
        (tmp_path / "scene-02.svg").symlink_to(tmp_path.parent / "outside.svg")
    (tmp_path / "storyboard.json").write_text(json.dumps(data))
    with pytest.raises((exporter.ExportError, OSError)):
        exporter.load_storyboard(tmp_path)


@pytest.mark.parametrize("fps", [0, 61, 25.5, True])
def test_invalid_fps_does_not_create_outputs(tmp_path, fps):
    with pytest.raises(exporter.ExportError, match="FPS"):
        exporter.export_storyboard(tmp_path, fps=fps)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["capture", "encode", "probe"])
def test_failure_cleans_workspace_and_preserves_previous_output(tmp_path, monkeypatch, failure):
    write_storyboard(tmp_path)
    output = tmp_path / "final-video.mp4"
    output.write_bytes(b"previous-good-video")
    monkeypatch.setattr(exporter, "find_chrome", lambda: "/chrome")
    monkeypatch.setattr(exporter.shutil, "which", lambda _: "/ffmpeg")

    @contextmanager
    def fake_chrome(workspace, executable):
        (workspace / "chrome-profile").mkdir()
        yield object()

    def capture(*args):
        if failure == "capture":
            raise exporter.ExportError("capture failed")
        return []

    def run(command, **kwargs):
        assert kwargs.get("shell", False) is False
        Path(command[-1]).write_bytes(b"encoded-video")
        return subprocess.CompletedProcess(command, 1 if failure == "encode" else 0, "", "encode failed")

    monkeypatch.setattr(exporter, "open_chrome", fake_chrome)
    monkeypatch.setattr(exporter, "capture_scenes", capture)
    monkeypatch.setattr(exporter.subprocess, "run", run)
    monkeypatch.setattr(exporter, "inspect_video", lambda *args: (_ for _ in ()).throw(exporter.ExportError("probe failed")))
    with pytest.raises(exporter.ExportError):
        exporter.export_storyboard(tmp_path)
    assert output.read_bytes() == b"previous-good-video"
    assert not list(tmp_path.glob("askhype-storyboard-*"))


def test_ffprobe_checks_actual_media_and_rejects_wrong_duration(tmp_path, monkeypatch):
    write_storyboard(tmp_path)
    plan, _ = exporter.load_storyboard(tmp_path)
    data = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280,
                         "height": 720, "pix_fmt": "yuv420p", "avg_frame_rate": "25/1", "nb_frames": "250"}],
            "format": {"duration": "10.0", "size": "12345"}}
    monkeypatch.setattr(exporter.shutil, "which", lambda _: "/ffprobe")
    monkeypatch.setattr(exporter.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(data), ""))
    assert exporter.inspect_video(tmp_path / "video.mp4", plan, 25)["validation"] == "passed"
    data["format"]["duration"] = "8.8"
    with pytest.raises(exporter.ExportError, match="output validation"):
        exporter.inspect_video(tmp_path / "video.mp4", plan, 25)


def test_ffprobe_missing_is_explicit(tmp_path, monkeypatch):
    write_storyboard(tmp_path)
    plan, _ = exporter.load_storyboard(tmp_path)
    output = tmp_path / "video.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(exporter.shutil, "which", lambda _: None)
    report = exporter.inspect_video(output, plan, 25)
    assert "unavailable" in report["validation"]
    assert "codec" not in report


@pytest.mark.skipif(os.environ.get("RUN_STORYBOARD_VIDEO_INTEGRATION") != "1",
                    reason="Opt in to local Chromium/FFmpeg capture with RUN_STORYBOARD_VIDEO_INTEGRATION=1")
def test_real_capture_seeks_deterministically_and_exports_all_transitions(tmp_path):
    write_storyboard(tmp_path)
    plan, sources = exporter.load_storyboard(tmp_path)
    workspace = tmp_path / "work"
    workspace.mkdir()
    page = exporter.write_capture_page(workspace, sources)
    with exporter.open_chrome(workspace, exporter.find_chrome()) as chrome:
        metrics = exporter.capture_scenes(chrome, workspace, page, plan, 10)
        assert all(scene["css_animations"] == 1 for scene in metrics)
        before = (workspace / "scene-01/frame-000004.png").read_bytes()
        after = (workspace / "scene-01/frame-000014.png").read_bytes()
        first, second = Image.open(BytesIO(before)), Image.open(BytesIO(after))
        assert sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) > 0.5
        # Seeking backwards must reproduce identical pixels, including the
        # authored positive delay and alternate-reverse playback direction.
        chrome.evaluate("window.exportScenes.forEach((s,i) => s.frame.style.visibility = i === 0 ? 'visible' : 'hidden');"
                        "window.exportScenes[0].animations[0].currentTime = 400")
        repeated = chrome.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        assert ImageChops.difference(first.convert("RGB"), Image.open(BytesIO(base64.b64decode(repeated["data"]))).convert("RGB")).getbbox() is None

    output = tmp_path / "video.mp4"
    result = subprocess.run(exporter.ffmpeg_command(shutil.which("ffmpeg"), workspace, output, plan, 10),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert exporter.inspect_video(output, plan, 10)["duration_seconds"] == 10

    def pixel_at(seconds, x=640):
        result = subprocess.run([
            shutil.which("ffmpeg"), "-v", "error", "-ss", str(seconds), "-i", str(output),
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-threads", "1", "-",
        ], capture_output=True, timeout=30, check=True)
        return Image.open(BytesIO(result.stdout)).convert("RGB").getpixel((x, 100))

    # Full scenes at their scheduled times; crossfade blends both colors and
    # slide has outgoing/incoming colors on opposite sides of the same frame.
    assert pixel_at(1)[0] > 230
    assert pixel_at(3)[1] > 230
    assert pixel_at(5)[2] > 230
    crossfade = pixel_at(2.3)
    assert crossfade[0] > 60 and crossfade[1] > 60
    assert pixel_at(4.3, 100)[1] > 200
    assert pixel_at(4.3, 1180)[2] > 200
    assert max(pixel_at(0)) < 20
    assert max(pixel_at(9.9)) < 20
