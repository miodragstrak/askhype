from __future__ import annotations

import math
import logging
import shutil
import subprocess
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

from app.schemas.animations import AnimationCharacter, AnimationObject, AnimationPlan

WIDTH, HEIGHT, FPS = 1280, 720, 25
MAX_DURATION_SECONDS, MAX_FRAMES = 15, 375
RENDER_TIMEOUT_SECONDS, FFMPEG_TIMEOUT_SECONDS = 45, 45
WORKSPACE_ROOT = Path("/tmp/askhype-animation")
logger = logging.getLogger(__name__)

COLORS = {
    "blue": "#246BFD", "yellow": "#FFD43B", "red": "#EF4444", "green": "#22C55E",
    "purple": "#8B5CF6", "orange": "#F97316", "pink": "#EC4899", "brown": "#92400E",
    "gray": "#64748B", "white": "#F8FAFC", "black": "#172033",
}


class CartoonRenderError(RuntimeError): pass
class CartoonRenderTimeout(CartoonRenderError): pass


@dataclass(frozen=True)
class RenderState:
    x: float
    y: float
    opacity: float = 1
    body_offset_y: float = 0
    head_rotation: float = 0
    eye_x: float = 0
    eye_y: float = 0
    right_upper_arm: float = 20
    right_forearm: float = 20
    expression: str = "neutral"
    bubble: tuple[str, bool] | None = None


@dataclass(frozen=True)
class RenderArtifact:
    workspace: Path
    output_path: Path
    frame_count: int
    render_seconds: float
    file_size: int


def _ease(value: float) -> float:
    value = min(max(value, 0), 1)
    return value * value * (3 - 2 * value)


def state_at(plan: AnimationPlan, actor_id: str, seconds: float) -> RenderState:
    actor = next(item for item in [*plan.characters, *plan.objects] if item.id == actor_id)
    events = sorted((item for item in plan.timeline if item.target_id == actor_id), key=lambda item: item.start)
    values: dict[str, Any] = {
        "x": actor.x, "y": actor.y,
        "opacity": 0 if any(item.action == "appear" and seconds < item.start for item in events) else 1,
        "body_offset_y": 0, "head_rotation": 0, "eye_x": 0, "eye_y": 0,
        "right_upper_arm": 20, "right_forearm": 20,
        "expression": "surprised" if getattr(actor, "expression", None) == "surprised" else
                      "smile" if getattr(actor, "expression", None) == "happy" else "neutral",
        "bubble": None,
    }
    for event in events:
        if seconds < event.start:
            continue
        progress = min((seconds - event.start) / event.duration, 1)
        eased, active = _ease(progress), progress < 1
        if event.action == "move":
            target_x = event.parameters.x if event.parameters.x is not None else values["x"]
            target_y = event.parameters.y if event.parameters.y is not None else values["y"]
            values["x"] += (target_x - values["x"]) * eased
            values["y"] += (target_y - values["y"]) * eased
        elif event.action == "enter_left": values["x"] = actor.x - (1 - eased) * 115
        elif event.action == "enter_right": values["x"] = actor.x + (1 - eased) * 115
        elif event.action == "exit_left": values["x"] = actor.x - eased * 115
        elif event.action == "exit_right": values["x"] = actor.x + eased * 115
        elif event.action == "appear": values["opacity"] = eased
        elif event.action == "disappear": values["opacity"] = 1 - eased
        if not active:
            continue
        if event.action == "wave":
            values["right_upper_arm"] = 150
            values["right_forearm"] = 155 + math.sin(progress * math.pi * 8) * 22
        elif event.action == "bounce": values["body_offset_y"] -= math.sin(progress * math.pi) * 58
        elif event.action == "nod": values["head_rotation"] += math.sin(progress * math.pi * 4) * 9
        elif event.action == "shake": values["head_rotation"] += math.sin(progress * math.pi * 6) * 13
        elif event.action == "look_left": values["head_rotation"], values["eye_x"] = -6, -4
        elif event.action == "look_right": values["head_rotation"], values["eye_x"] = 6, 4
        elif event.action == "look_up": values["head_rotation"], values["eye_y"] = -6, -4
        elif event.action == "smile": values["expression"] = "smile"
        elif event.action == "surprised": values["expression"] = "surprised"
        elif event.action in {"speech", "thought"} and event.parameters.text:
            values["bubble"] = (event.parameters.text, event.action == "thought")
    return RenderState(**values)


def create_workspace() -> Path:
    WORKSPACE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="render-", dir=WORKSPACE_ROOT))


def ffmpeg_command(workspace: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
        "-i", str(workspace / "frame_%04d.png"), "-c:v", "libx264", "-preset", "medium",
        "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
    ]


def render_video(
    plan: AnimationPlan,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> RenderArtifact:
    if plan.duration_seconds > MAX_DURATION_SECONDS:
        raise CartoonRenderError("Animation duration exceeds the render limit.")
    frame_count = math.ceil(plan.duration_seconds * FPS)
    if frame_count > MAX_FRAMES:
        raise CartoonRenderError("Animation frame count exceeds the render limit.")
    workspace = create_workspace()
    output_path = workspace / "output.mp4"
    started = time.monotonic()
    try:
        for index in range(frame_count):
            if time.monotonic() - started > RENDER_TIMEOUT_SECONDS:
                raise CartoonRenderTimeout("Frame rendering timed out.")
            render_frame(plan, index / FPS).save(workspace / f"frame_{index + 1:04d}.png", "PNG")
        try:
            completed = runner(
                ffmpeg_command(workspace, output_path), capture_output=True, text=True,
                timeout=FFMPEG_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CartoonRenderTimeout("MP4 encoding timed out.") from exc
        if completed.returncode != 0 or not output_path.is_file():
            summary = (completed.stderr or "FFmpeg exited without diagnostic output.").strip().splitlines()[-1]
            logger.warning("Cartoon MP4 encoding failed: %s", summary.replace(str(workspace), "<render-workspace>")[:240])
            raise CartoonRenderError("FFmpeg could not encode the animation.")
        for frame in workspace.glob("frame_*.png"):
            frame.unlink()
        return RenderArtifact(
            workspace=workspace, output_path=output_path, frame_count=frame_count,
            render_seconds=time.monotonic() - started, file_size=output_path.stat().st_size,
        )
    except Exception:
        cleanup_workspace(workspace)
        raise


def cleanup_workspace(workspace: Path) -> None:
    try:
        workspace.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise CartoonRenderError("Refusing to clean an unsafe render path.") from exc
    shutil.rmtree(workspace, ignore_errors=True)


def render_frame(plan: AnimationPlan, seconds: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#DDF2FF")
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_background(draw, plan.background.type)
    states = {item.id: state_at(plan, item.id, seconds) for item in [*plan.objects, *plan.characters]}
    for obj in plan.objects:
        if obj.type in {"cloud", "star", "tree"}: _draw_object(draw, obj, states[obj.id])
    for character in plan.characters:
        _draw_character(draw, character, states[character.id])
    for obj in plan.objects:
        if obj.type not in {"cloud", "star", "tree"}: _draw_object(draw, obj, states[obj.id])
    for character in plan.characters:
        if states[character.id].bubble: _draw_bubble(draw, states[character.id])
    return image


def _draw_background(draw: ImageDraw.ImageDraw, kind: str) -> None:
    skies = {"space": "#10162F", "room": "#FFF4D6", "office": "#EAF0F8", "school": "#E6F0FF", "abstract": "#E7E2FF"}
    sky = skies.get(kind, "#BDE7FF")
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=sky)
    if kind == "space":
        for x, y in ((80, 90), (220, 160), (420, 65), (750, 120), (1020, 72), (1170, 200)):
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#FFF4B8")
        draw.rectangle((0, 570, WIDTH, HEIGHT), fill="#272C55")
    elif kind in {"room", "office", "school"}:
        draw.rectangle((0, 510, WIDTH, HEIGHT), fill="#D8C6A5")
        draw.line((0, 510, WIDTH, 510), fill="#A68D67", width=5)
        draw.rounded_rectangle((70, 90, 330, 300), 18, fill="#D7F2FF", outline="#FFFFFF", width=12)
    else:
        draw.ellipse((-160, 400, 600, 760), fill="#7FD38A")
        draw.ellipse((370, 390, 1400, 800), fill="#68C37A")
        draw.rectangle((0, 570, WIDTH, HEIGHT), fill="#71C985")
        draw.ellipse((1020, 70, 1120, 170), fill="#FFD65A")


def _rgba(hex_color: str, opacity: float) -> tuple[int, int, int, int]:
    color = hex_color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4)) + (round(opacity * 255),)


def _point(origin: tuple[float, float], angle: float, length: float) -> tuple[float, float]:
    radians = math.radians(angle)
    return origin[0] + math.sin(radians) * length, origin[1] + math.cos(radians) * length


def _limb(draw: ImageDraw.ImageDraw, shoulder: tuple[float, float], upper_angle: float, lower_angle: float,
          color: tuple[int, int, int, int], scale: float) -> None:
    elbow = _point(shoulder, upper_angle, 47 * scale)
    hand = _point(elbow, lower_angle, 40 * scale)
    draw.line((*shoulder, *elbow), fill=color, width=round(17 * scale), joint="curve")
    draw.ellipse((elbow[0] - 8 * scale, elbow[1] - 8 * scale, elbow[0] + 8 * scale, elbow[1] + 8 * scale), fill=color)
    draw.line((*elbow, *hand), fill=color, width=round(15 * scale))
    draw.ellipse((hand[0] - 10 * scale, hand[1] - 10 * scale, hand[0] + 10 * scale, hand[1] + 10 * scale), fill=color)


def _draw_character(draw: ImageDraw.ImageDraw, actor: AnimationCharacter, state: RenderState) -> None:
    if state.opacity <= 0: return
    x, floor = state.x * WIDTH / 100, state.y * HEIGHT / 100 + state.body_offset_y
    scale = actor.scale * (0.82 if actor.type == "child" else 1)
    body, accent = _rgba(COLORS[actor.appearance.body_color], state.opacity), _rgba(COLORS[actor.appearance.accent_color], state.opacity)
    if actor.type == "animal": return _draw_animal(draw, x, floor, scale, body, accent, state)
    creature, robot = actor.type == "creature", actor.type == "robot"
    torso_top = floor - 150 * scale
    left_shoulder, right_shoulder = (x - 32 * scale, torso_top + 22 * scale), (x + 32 * scale, torso_top + 22 * scale)
    _limb(draw, left_shoulder, -24, -18, body, scale)
    _limb(draw, right_shoulder, state.right_upper_arm, state.right_forearm, body, scale)
    draw.rounded_rectangle((x - 38 * scale, torso_top, x + 38 * scale, floor - 65 * scale), radius=18 * scale, fill=accent)
    draw.line((x - 18 * scale, floor - 70 * scale, x - 22 * scale, floor), fill=body, width=round(20 * scale))
    draw.line((x + 18 * scale, floor - 70 * scale, x + 22 * scale, floor), fill=body, width=round(20 * scale))
    head_center = (
        x + state.head_rotation * .65 * scale,
        torso_top - 49 * scale - abs(state.head_rotation) * .3 * scale,
    )
    if creature:
        draw.ellipse((head_center[0] - 50 * scale, head_center[1] - 43 * scale, head_center[0] + 50 * scale, head_center[1] + 43 * scale), fill=body)
    else:
        draw.rounded_rectangle((head_center[0] - 44 * scale, head_center[1] - 42 * scale, head_center[0] + 44 * scale, head_center[1] + 42 * scale), radius=(12 if robot else 40) * scale, fill=body)
    if robot:
        draw.line((x, head_center[1] - 42 * scale, x, head_center[1] - 62 * scale), fill=accent, width=5)
        draw.ellipse((x - 7, head_center[1] - 69 * scale, x + 7, head_center[1] - 55 * scale), fill=accent)
        draw.rounded_rectangle((x - 18 * scale, torso_top + 18 * scale, x + 18 * scale, torso_top + 43 * scale), 6, fill=body)
    elif actor.appearance.hair_style != "none":
        draw.pieslice((head_center[0] - 45 * scale, head_center[1] - 48 * scale, head_center[0] + 45 * scale, head_center[1] + 37 * scale), 180, 360, fill=accent)
    _draw_face(draw, head_center, scale, state, robot, body)


def _draw_face(draw: ImageDraw.ImageDraw, center: tuple[float, float], scale: float, state: RenderState,
               robot: bool, color: tuple[int, int, int, int]) -> None:
    eye_y = center[1] - 7 * scale + state.eye_y * scale
    for offset in (-15, 15):
        eye_x = center[0] + (offset + state.eye_x) * scale
        radius = (6 if state.expression == "surprised" else 4) * scale
        draw.ellipse((eye_x - radius, eye_y - radius, eye_x + radius, eye_y + radius), fill="#172033")
    mouth_y = center[1] + 17 * scale
    if state.expression == "surprised": draw.ellipse((center[0] - 7 * scale, mouth_y - 6 * scale, center[0] + 7 * scale, mouth_y + 8 * scale), fill="#172033")
    elif state.expression == "smile": draw.arc((center[0] - 16 * scale, mouth_y - 12 * scale, center[0] + 16 * scale, mouth_y + 12 * scale), 10, 170, fill="#172033", width=max(2, round(4 * scale)))
    else: draw.line((center[0] - 10 * scale, mouth_y, center[0] + 10 * scale, mouth_y), fill="#172033", width=max(2, round(3 * scale)))
    if not robot:
        draw.arc((center[0] - 26 * scale, center[1] - 24 * scale, center[0] - 4 * scale, center[1] - 10 * scale), 190, 345, fill=color, width=2)
        draw.arc((center[0] + 4 * scale, center[1] - 24 * scale, center[0] + 26 * scale, center[1] - 10 * scale), 195, 350, fill=color, width=2)


def _draw_animal(draw: ImageDraw.ImageDraw, x: float, floor: float, scale: float,
                 body: tuple[int, int, int, int], accent: tuple[int, int, int, int], state: RenderState) -> None:
    draw.ellipse((x - 65 * scale, floor - 95 * scale, x + 50 * scale, floor - 25 * scale), fill=body)
    head = (
        x - 58 * scale + state.head_rotation * .7 * scale,
        floor - 102 * scale - abs(state.head_rotation) * .4 * scale,
    )
    draw.ellipse((head[0] - 40 * scale, head[1] - 38 * scale, head[0] + 40 * scale, head[1] + 38 * scale), fill=accent)
    draw.polygon(((head[0] - 31 * scale, head[1] - 25 * scale), (head[0] - 47 * scale, head[1] - 59 * scale), (head[0] - 10 * scale, head[1] - 36 * scale)), fill=body)
    draw.polygon(((head[0] + 31 * scale, head[1] - 25 * scale), (head[0] + 47 * scale, head[1] - 59 * scale), (head[0] + 10 * scale, head[1] - 36 * scale)), fill=body)
    for leg_x in (-42, -10, 28, 45): draw.line((x + leg_x * scale, floor - 35 * scale, x + leg_x * scale, floor), fill=body, width=round(14 * scale))
    draw.arc((x + 25 * scale, floor - 112 * scale, x + 100 * scale, floor - 40 * scale), 195, 350, fill=body, width=round(13 * scale))
    _draw_face(draw, head, scale * .78, state, False, body)


def _draw_object(draw: ImageDraw.ImageDraw, obj: AnimationObject, state: RenderState) -> None:
    if state.opacity <= 0: return
    x, y, scale = state.x * WIDTH / 100, state.y * HEIGHT / 100 + state.body_offset_y, obj.scale
    color = _rgba(COLORS[obj.color], state.opacity)
    if obj.type == "rocket":
        draw.polygon(((x, y - 65 * scale), (x - 30 * scale, y + 30 * scale), (x, y + 18 * scale), (x + 30 * scale, y + 30 * scale)), fill=color)
        draw.ellipse((x - 13 * scale, y - 30 * scale, x + 13 * scale, y - 4 * scale), fill="#BDE7FF")
        draw.polygon(((x - 13 * scale, y + 23 * scale), (x, y + 58 * scale), (x + 13 * scale, y + 23 * scale)), fill="#FFD43B")
    elif obj.type == "tree":
        draw.rectangle((x - 12 * scale, y - 90 * scale, x + 12 * scale, y), fill="#8B5A2B")
        draw.ellipse((x - 55 * scale, y - 150 * scale, x + 55 * scale, y - 55 * scale), fill=color)
    elif obj.type == "cloud":
        draw.ellipse((x - 55 * scale, y - 25 * scale, x + 55 * scale, y + 25 * scale), fill=color)
    elif obj.type == "star":
        draw.regular_polygon((x, y, 30 * scale), 5, rotation=-18, fill=color)
    else:
        draw.rounded_rectangle((x - 30 * scale, y - 30 * scale, x + 30 * scale, y + 30 * scale), 12 * scale, fill=color)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        if Path(path).is_file(): return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_bubble(draw: ImageDraw.ImageDraw, state: RenderState) -> None:
    text, thought = state.bubble or ("", False)
    wrapped = "\n".join(textwrap.wrap(text, width=28)[:4])
    font = _font(25)
    box = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=5, align="center")
    width, height = min(max(box[2] - box[0] + 44, 180), 410), min(max(box[3] - box[1] + 34, 70), 170)
    x = min(max(state.x * WIDTH / 100 - width / 2, 18), WIDTH - width - 18)
    y = max(state.y * HEIGHT / 100 - 310, 20)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height / 2 if thought else 22, fill="#FFFFFFF2", outline="#B7C4D6", width=3)
    draw.multiline_text((x + width / 2, y + height / 2), wrapped, font=font, fill="#172033", anchor="mm", spacing=5, align="center")
    if thought:
        draw.ellipse((x + 30, y + height + 8, x + 46, y + height + 24), fill="#FFFFFFF2")
    else:
        draw.polygon(((x + 48, y + height), (x + 70, y + height), (x + 57, y + height + 24)), fill="#FFFFFFF2")
