import asyncio
import json
import time

from app.schemas.generative_svg import StoryboardPlan
from scripts import generate_svg_animation_poc as cli


class _Provider:
    model = "test-model"

    async def generate_storyboard(self, prompt: str, duration_seconds: int) -> StoryboardPlan:
        assert prompt == "Test priča"
        assert duration_seconds == 15
        return StoryboardPlan.model_validate({
            "title": "Test", "total_duration_seconds": 15,
            "shared_art_direction": {
                "title": "Test", "duration_seconds": 10, "scene_description": "Plavo biće leti",
                "characters": [], "objects": [], "background_description": "Svemir",
                "composition": "Srednji plan", "visual_style": "Glow", "shape_language": "Zaobljeno",
                "palette": ["#101830", "#4f7cff", "#ffd166"], "lighting": "Meki sjaj",
                "line_treatment": "Meke linije", "depth_style": "Slojevito", "mood": "Sanjivo",
                "motion_style": "Blago", "timeline_beats": [{"start": 0, "duration": 10, "description": "Let", "motion": "Lebdenje"}],
            },
            "recurring_subjects": [{"id": "hero", "name": "Plavo biće", "kind": "creature", "appearance": "Meko plavo biće"}],
            "scenes": [
                {"id": f"scene_{index}", "duration_seconds": 5, "description": "Plavo biće leti", "environment": "Svemir", "subject_ids": ["hero"], "action": "Lebdi", "mood": "Sanjivo", "composition": "Srednji plan", "transition_in": "fade", "transition_out": "crossfade"}
                for index in range(1, 4)
            ],
        })


def test_storyboard_cli_writes_bounded_scene_artifacts_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "render_svg_preview", lambda source, target, **kwargs: target.write_bytes(b"png") or 0.01)
    metrics_path = tmp_path / "metrics.json"
    asyncio.run(cli._generate_storyboard_report(
        _Provider(), "Test priča", 15, tmp_path, metrics_path, time.monotonic(),
    ))
    metrics = json.loads(metrics_path.read_text())
    assert metrics["total_duration_seconds"] == 15
    assert metrics["scene_count"] == 3
    assert metrics["recurring_subject_ids"] == ["hero"]
    assert metrics["sanitizer_quality_passed"] is True
    assert all(scene["quality_passed"] for scene in metrics["scenes"])
    assert (tmp_path / "storyboard.json").is_file()
    for index in range(1, 4):
        assert (tmp_path / f"scene-{index:02d}.svg").is_file()
        assert (tmp_path / f"scene-{index:02d}.png").is_file()
