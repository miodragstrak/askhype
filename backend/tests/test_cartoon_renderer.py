from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from PIL import Image

from app.renderers import cartoon_renderer as renderer
from app.renderers.cartoon_renderer import (
    CartoonRenderError, CartoonRenderTimeout, FPS, HEIGHT, MAX_FRAMES, WIDTH,
    cleanup_workspace, create_workspace, ffmpeg_command, render_frame, render_video, state_at,
)
from app.schemas.animations import (
    AnimationAppearance, AnimationBackground, AnimationCharacter, AnimationPlan,
    TimelineEvent, TimelineParameters,
)


def plan(duration: float = 10) -> AnimationPlan:
    return AnimationPlan(
        title="Test", duration_seconds=duration,
        background=AnimationBackground(type="park", description="Park"),
        characters=[
            AnimationCharacter(
                id="woman", type="person", name="Žena", x=20, y=82,
                appearance=AnimationAppearance(body_color="pink", accent_color="purple", hair_style="long"),
            ),
            AnimationCharacter(
                id="child", type="child", name="Dete", x=50, y=84,
                appearance=AnimationAppearance(body_color="blue", accent_color="yellow"),
            ),
            AnimationCharacter(
                id="dog", type="animal", name="Pas", x=72, y=85,
                appearance=AnimationAppearance(body_color="brown", accent_color="orange"),
            ),
        ],
        timeline=[
            TimelineEvent(start=0, duration=2, target_id="woman", action="move", parameters=TimelineParameters(x=60)),
            TimelineEvent(start=2, duration=2, target_id="woman", action="wave"),
            TimelineEvent(start=2, duration=2, target_id="child", action="bounce"),
            TimelineEvent(start=4, duration=2, target_id="dog", action="look_up"),
            TimelineEvent(start=6, duration=2, target_id="child", action="speech", parameters=TimelineParameters(text="Zdravo!")),
        ],
    )


def test_state_is_deterministic_and_movement_is_eased():
    first = state_at(plan(), "woman", 1)
    assert first == state_at(plan(), "woman", 1)
    assert first.x == pytest.approx(40)


def test_wave_bounce_look_up_and_bubble_timing():
    animation = plan()
    wave_a, wave_b = state_at(animation, "woman", 2.2), state_at(animation, "woman", 2.35)
    assert wave_a.right_upper_arm == 150
    assert wave_a.right_forearm != wave_b.right_forearm
    assert state_at(animation, "child", 3).body_offset_y < 0
    dog = state_at(animation, "dog", 5)
    assert dog.head_rotation == -6 and dog.eye_y == -4
    assert state_at(animation, "child", 5.9).bubble is None
    assert state_at(animation, "child", 7).bubble == ("Zdravo!", False)


def test_frame_has_fixed_resolution_and_controlled_content():
    frame = render_frame(plan(), 3)
    assert frame.size == (WIDTH, HEIGHT) and frame.mode == "RGB"


def test_limits_match_poc_contract():
    assert FPS == 25 and MAX_FRAMES == 375
    with pytest.raises(CartoonRenderError, match="duration"):
        render_video(SimpleNamespace(duration_seconds=16))


def test_workspace_is_isolated_and_cleanup_rejects_unsafe_path(tmp_path):
    workspace = create_workspace()
    assert workspace.parent == renderer.WORKSPACE_ROOT and workspace.name.startswith("render-")
    cleanup_workspace(workspace)
    assert not workspace.exists()
    with pytest.raises(CartoonRenderError, match="unsafe"):
        cleanup_workspace(tmp_path)


def test_ffmpeg_command_is_fixed_and_contains_no_shell(tmp_path):
    command = ffmpeg_command(tmp_path, tmp_path / "output.mp4")
    assert command[0] == "ffmpeg"
    assert "libx264" in command and "yuv420p" in command and "+faststart" in command
    assert all(isinstance(item, str) for item in command)


def test_render_cleans_frames_and_invokes_runner_without_shell(monkeypatch, tmp_path):
    workspace = tmp_path / "render-safe"
    workspace.mkdir()
    monkeypatch.setattr(renderer, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(renderer, "create_workspace", lambda: workspace)
    monkeypatch.setattr(renderer, "render_frame", lambda *_: Image.new("RGB", (8, 8), "white"))
    captured = {}
    def runner(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        Path(command[-1]).write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="")
    artifact = render_video(plan().model_copy(update={"duration_seconds": 1, "timeline": []}), runner=runner)
    assert artifact.frame_count == 25 and artifact.output_path.read_bytes() == b"mp4"
    assert not list(workspace.glob("frame_*.png"))
    assert "shell" not in captured["kwargs"]
    cleanup_workspace(workspace)


def test_ffmpeg_timeout_is_safe_and_workspace_is_removed(monkeypatch, tmp_path):
    workspace = tmp_path / "render-timeout"
    workspace.mkdir()
    monkeypatch.setattr(renderer, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(renderer, "create_workspace", lambda: workspace)
    monkeypatch.setattr(renderer, "render_frame", lambda *_: Image.new("RGB", (8, 8), "white"))
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, stderr="private path and provider content")
    with pytest.raises(CartoonRenderTimeout, match="timed out"):
        render_video(plan().model_copy(update={"duration_seconds": 1, "timeline": []}), runner=timeout)
    assert not workspace.exists()
