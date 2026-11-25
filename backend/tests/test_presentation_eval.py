import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types

from app.schemas.documents import DocumentMetadata, ExtractedDocument
from scripts import presentation_eval as evaluation
from scripts.presentation_qa import fixtures


def _fixture(name):
    return next(plan for key, plan, _ in fixtures() if key == name)


def _run(output, plan, document=None):
    async def load():
        return plan

    case = {"id": "operations-decision", "prompt": f"Create {len(plan.slides)} slides in English."}
    return asyncio.run(evaluation.evaluate(case, document, output, load, mode="live", planner_config={}))


def _metrics(output):
    return json.loads((output / "metrics.json").read_text())


def test_plan_is_present_even_when_downstream_rendering_fails(tmp_path, monkeypatch):
    plan = _fixture("media-executive")
    original = evaluation.build_presentation

    def assert_saved(*args):
        assert json.loads((tmp_path / "plan.json").read_text())["title"] == plan.title
        return original(*args)

    monkeypatch.setattr(evaluation, "build_presentation", assert_saved)
    plan.slides[1].layout = "process"
    plan.slides[1].bullets = ["One step only"]
    assert not _run(tmp_path, plan)
    assert (tmp_path / "plan.json").exists()
    assert not (tmp_path / "deck.pptx").exists()
    metrics = _metrics(tmp_path)
    assert metrics["schema_valid"] is True
    assert metrics["failure_stage"] == "select_layout"
    assert metrics["failed_validation_rule"] == "diagram_steps"
    assert metrics["slide_index"] == 2
    assert metrics["requested_layout"] == metrics["selected_layout"] == "process"
    assert "at least two" in metrics["exception_message"]


def test_unknown_exception_details_are_not_copied(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("test-secret-never-in-diagnostics")

    monkeypatch.setattr(evaluation, "build_presentation", fail)
    assert not _run(tmp_path, _fixture("media-executive"))
    for filename in ("metrics.json", "traceback.txt"):
        assert "test-secret-never-in-diagnostics" not in (tmp_path / filename).read_text()
    assert (tmp_path / "plan.json").exists()


def test_offline_replay_uses_saved_evidence_without_initializing_provider(tmp_path, monkeypatch):
    first = tmp_path / "original"
    first.mkdir()
    replay = tmp_path / "replay"
    plan = _fixture("quantitative")
    document = ExtractedDocument("synthetic.csv", "csv", "Pilot A: 12 units. Pilot B: 18 units.",
                                 DocumentMetadata(extracted_characters=39))
    assert _run(first, plan, document)
    for name in ("plan.json", "metrics.json", "context.json", "deck.pptx"):
        assert (first / name).is_file()

    def forbid(*args, **kwargs):
        pytest.fail("Offline replay initialized Gemini")

    monkeypatch.setattr(evaluation, "GeminiProvider", forbid)
    monkeypatch.setattr(evaluation, "extract_document", forbid)
    monkeypatch.setattr(sys, "argv", ["presentation_eval", "--replay-plan", str(first / "plan.json"),
                                    "--brief", "operations-decision", "--output", str(replay)])
    assert evaluation.main() == 0
    assert (replay / "deck.pptx").exists()
    assert _metrics(replay)["attempts"] == []
    assert _metrics(replay)["planning_seconds"] == 0


def test_ragged_chart_fails_structure_before_evidence(tmp_path):
    plan = _fixture("quantitative")
    plan.slides[2].rows[0].append("999")
    document = ExtractedDocument("synthetic.csv", "csv", "12 units and 18 units.",
                                 DocumentMetadata(extracted_characters=22))
    assert not _run(tmp_path, plan, document)
    metrics = _metrics(tmp_path)
    assert metrics["failure_stage"] == "verify_evidence"
    assert metrics["failed_validation_rule"] == "table_dimensions"
    assert metrics["slide_index"] == 3
    assert metrics["requested_layout"] == "chart"
    assert metrics["selected_layout"] is None


def test_meter_captures_request_and_finish_metadata():
    class Models:
        async def generate_content(self, **kwargs):
            return SimpleNamespace(
                candidates=[types.Candidate(finish_reason=types.FinishReason.MAX_TOKENS)],
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=913, candidates_token_count=1684, thoughts_token_count=2397,
                    total_token_count=4994,
                ),
            )

    meter = evaluation.Meter(Models(), 60)
    asyncio.run(meter.generate_content(model="gemini-3.8-flash", config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )))
    attempt, = meter.attempts
    assert attempt["model"] == "gemini-3.8-flash"
    assert attempt["timeout_seconds"] == 60
    assert attempt["thinking_config"] == {"thinking_level": "LOW"}
    assert attempt["finish_reason"] == "MAX_TOKENS"
    assert attempt["output_exhausted"] is True
    assert attempt["candidates_token_count"] == 1684
    assert attempt["thoughts_token_count"] == 2397
    assert attempt["total_token_count"] == 4994


@pytest.mark.parametrize("mode,expected_slides", [("COVER", [1]), ("ENHANCED", [1, 2])])
def test_image_only_replay_validates_native_deck_before_image_requests(tmp_path, monkeypatch, mode, expected_slides):
    from app.schemas.presentations import IllustrationRequest
    from app.services.presentation_illustrations import resolve_illustrations, select_illustrations

    first = tmp_path / "original"
    first.mkdir()
    output = tmp_path / "image-only"
    plan = _fixture("media-executive")
    plan.illustrations = [
        IllustrationRequest(
            slide_index=index, purpose="Explain the strategy", subject="Regional broadcast studio",
            composition="Focus on a single studio", visual_style="Editorial",
            palette="Navy", aspect_ratio="16:9", crop_region=crop,
        )
        for index, crop in [(1, "cover_right"), (2, "split_right")]
    ]
    assert _run(first, plan)
    order = []
    build = evaluation.build_presentation

    def render_native(*args):
        result = build(*args)
        order.append("native")
        return result

    class FailingImageProvider:
        async def generate(self, request):
            order.append(request.slide_index)
            raise RuntimeError("Private diagnostic detail")

    async def resolve(plan, config, layouts, *, attempts):
        assert config.presentation_illustration_mode == mode
        assert [item.slide_index for item in select_illustrations(plan, mode, layouts)] == expected_slides
        return await resolve_illustrations(
            plan, mode, FailingImageProvider(), config.presentation_illustration_timeout_seconds, layouts,
            attempts=attempts,
        )

    def forbid(*args, **kwargs):
        pytest.fail("Image-only replay initialized the presentation planner")

    monkeypatch.setattr(evaluation, "build_presentation", render_native)
    monkeypatch.setattr(evaluation, "resolve_gemini_illustrations", resolve)
    monkeypatch.setattr(evaluation, "GeminiProvider", forbid)
    monkeypatch.setattr(sys, "argv", ["presentation_eval", "--approved-image-only",
                                    "--replay-plan", str(first / "plan.json"),
                                    "--illustration-mode", mode, "--output", str(output)])
    assert evaluation.main() == 0
    assert order == ["native", *expected_slides]
    metrics = _metrics(output)
    assert metrics["attempts"] == []
    assert metrics["planning_seconds"] == 0
    assert metrics["used_native_deck"]
    assert metrics["illustration_seconds"] >= metrics["image_attempts"][0]["seconds"] > 0
    assert len(metrics["image_attempts"]) == 2
    if mode == "COVER":
        assert metrics["image_attempts"][1]["skip_reason"] == "mode_cover_only"
    else:
        assert metrics["image_attempts"][1]["status"] == "fallback"
    assert metrics["image_attempts"][0]["status"] == "fallback"
    assert "Private diagnostic detail" not in (output / "metrics.json").read_text()
