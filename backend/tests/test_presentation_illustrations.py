import asyncio
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import pytest

from app.providers.gemini import GeminiPresentationPlanEnvelope, prepare_gemini_presentation_schema, presentation_validation_issues
from app.schemas.presentations import IllustrationRequest
from app.services.presentation_diagnostics import PresentationDiagnostics
from app.services.presentation_generation import apply_illustrations, build_presentation
from app.services.presentation_illustrations import (
    GeminiIllustrationProvider, normalize_illustration, resolve_illustrations, select_illustrations,
)
from scripts.presentation_qa import image_fixtures


def asset(index, crop):
    return IllustrationRequest(
        slide_index=index, crop_region=crop, purpose="Editorial focus", subject="A fictional studio",
        composition="Centered subject", visual_style="Geometric", palette="Navy and gold", aspect_ratio="4:3",
    )


def deck():
    _, plan, _ = next(image_fixtures())
    plan.illustrations = [asset(1, "cover_right"), asset(2, "split_right"), asset(3, "split_right")]
    return plan


def raster():
    buffer = BytesIO()
    Image.new("RGB", (400, 300), "teal").save(buffer, format="PNG")
    return buffer.getvalue()


def resolved_layouts(plan):
    trace = PresentationDiagnostics()
    build_presentation(f"{len(plan.slides)} slides", plan, None, trace)
    return trace.resolved_layouts


def test_budget_and_eligible_slots():
    plan = deck()
    layouts = resolved_layouts(plan)
    assert select_illustrations(plan, "OFF", layouts) == []
    assert [item.slide_index for item in select_illustrations(plan, "COVER", layouts)] == [1]
    assert [item.slide_index for item in select_illustrations(plan, "ENHANCED", layouts)] == [1, 2, 3]
    plan.illustrations[2] = asset(6, "split_right")
    assert [item.slide_index for item in select_illustrations(plan, "ENHANCED", layouts)] == [1, 2]


def test_invalid_and_slow_images_use_native_fallback():
    plan = deck()

    class Provider:
        async def generate(self, request):
            if request.slide_index == 1:
                return raster()
            if request.slide_index == 2:
                return b"<svg/>"
            await asyncio.Event().wait()

    images = asyncio.run(resolve_illustrations(plan, "ENHANCED", Provider(), .1, resolved_layouts(plan)))
    assert set(images) == {1}
    native = build_presentation("6 slides", plan, None)
    with_picture = apply_illustrations(native, plan, None, images)
    rendered = Presentation(BytesIO(with_picture.content))
    assert any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in rendered.slides[0].shapes)
    assert any(shape.has_text_frame and plan.slides[0].title.split()[0] in shape.text
               for shape in rendered.slides[0].shapes)
    assert all(shape.shape_type != MSO_SHAPE_TYPE.PICTURE for shape in rendered.slides[1].shapes)


def test_image_adapter_requests_single_bounded_raster():
    data = raster()

    class Models:
        async def generate_content(self, **kwargs):
            assert "no text, letters" in kwargs["contents"]
            assert "functional diagrams" in kwargs["contents"]
            assert "rightmost 35 percent" in kwargs["contents"]
            config = kwargs["config"]
            assert config.candidate_count == 1
            assert config.response_modalities == ["IMAGE"]
            assert config.image_config.image_size == "1K"
            assert config.image_config.aspect_ratio == "16:9"
            assert config.http_options.timeout == 18_000
            return SimpleNamespace(
                usage_metadata=SimpleNamespace(total_token_count=321),
                parts=[SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/png", data=data))],
            )

    client = SimpleNamespace(models=Models())
    provider = GeminiIllustrationProvider(client, "image-test", 18)
    assert asyncio.run(provider.generate(asset(1, "full_bleed"))) == data
    assert provider.usage == {1: {"total_token_count": 321}}
    with pytest.raises(ValueError, match="size"):
        normalize_illustration(b"", "full_bleed")


def test_off_schema_preserves_existing_planner_contract():
    assert "illustrations" not in prepare_gemini_presentation_schema()["properties"]["plan"]["properties"]
    assert "illustrations" in prepare_gemini_presentation_schema(illustrations=True)["properties"]["plan"]["properties"]


def test_planner_diagnostics_mask_untrusted_fields_and_values():
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as caught:
        GeminiPresentationPlanEnvelope.model_validate({"plan": {
            "title": "Deck", "subtitle": "", "slides": [], "private-key": "private-value",
        }})
    issues = presentation_validation_issues(caught.value)
    assert {"location": ["plan", "slides"], "rule": "too_short"} in issues
    assert {"location": ["plan", "<unknown>"], "rule": "extra_forbidden"} in issues
    assert "private" not in str(issues)


def test_resolved_layout_controls_eligibility_and_reports_every_request():
    plan = deck()
    plan.slides[2].layout = "problem_solution"
    plan.slides[2].bullets = ["First option", "Second option", "Third option"]
    plan.slides[3].layout = "process"
    plan.slides[3].bullets = ["Prepare inputs", "Check the brief"]
    plan.illustrations = [asset(1, "cover_right"), asset(3, "split_right"),
                          asset(4, "split_right"), asset(2, "full_bleed")]
    attempts = []

    class Provider:
        model = "image-test"
        usage = {1: {"total_token_count": 123}}

        async def generate(self, request):
            await asyncio.sleep(.001)
            return raster()

    images = asyncio.run(resolve_illustrations(
        plan, "ENHANCED", Provider(), 1, resolved_layouts(plan), attempts=attempts,
    ))
    assert set(images) == {1, 3}
    assert [attempt["slide_index"] for attempt in attempts] == [1, 3, 4, 2]
    assert attempts[0]["token_usage"] == {"total_token_count": 123}
    assert attempts[1]["requested_layout"] == "problem_solution"
    assert attempts[1]["resolved_layout"] == "findings"
    assert attempts[1]["effective_crop_region"] == "split_right"
    assert attempts[1]["provider_attempted"] and not attempts[1]["native_fallback"]
    assert attempts[1]["seconds"] >= attempts[1]["provider_seconds"] > 0
    assert attempts[2]["skip_reason"] == "incompatible_resolved_layout"
    assert attempts[3]["skip_reason"] == "incompatible_crop"
    assert all(not attempt["provider_attempted"] for attempt in attempts[2:])

    native = build_presentation("6 slides", plan, None)
    deck_with_art = apply_illustrations(native, plan, None, images)
    slides = Presentation(BytesIO(deck_with_art.content)).slides
    for index in (0, 2):
        assert any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in slides[index].shapes)
    assert slides[2].notes_slide.notes_text_frame.text
    assert any(shape.has_text_frame and "Third option" in shape.text for shape in slides[2].shapes)


def test_enhanced_budget_runs_concurrently_and_skips_extra_eligible_requests():
    plan = deck()
    plan.illustrations.append(asset(4, "split_right"))
    layouts = resolved_layouts(plan)
    # Use an eligible fourth qualitative layout to exercise the budget boundary.
    plan.slides[3] = plan.slides[1].model_copy()
    layouts[4] = "findings"
    attempts = []

    class Provider:
        async def generate(self, request):
            started.add(request.slide_index)
            if len(started) == 3:
                ready.set()
            await ready.wait()
            return raster()

    async def run():
        nonlocal ready
        ready = asyncio.Event()
        return await resolve_illustrations(plan, "ENHANCED", Provider(), 1, layouts, attempts=attempts)

    ready = None
    started = set()
    assert set(asyncio.run(run())) == {1, 2, 3}
    assert started == {1, 2, 3}
    assert attempts[3]["skip_reason"] == "asset_budget"


@pytest.mark.parametrize("crop,aspect", [("cover_right", "3:4"), ("split_right", "4:3")])
def test_image_prompt_uses_slot_aspect_and_discards_conflicting_diagram_directions(crop, aspect):
    request = asset(1, crop).model_copy(update={
        "subject": "Media production workflow", "composition": "Label each process step",
        "visual_style": "Moderan vektorski dijagram", "aspect_ratio": "16:9",
    })

    class Models:
        async def generate_content(self, **kwargs):
            assert kwargs["config"].image_config.aspect_ratio == aspect
            prompt = kwargs["contents"]
            assert "Media production workflow" in prompt
            assert "Label each process step" not in prompt
            assert "Moderan vektorski dijagram" not in prompt
            assert "blank or abstract" in prompt
            assert "crop margins" in prompt
            return SimpleNamespace(parts=[SimpleNamespace(
                inline_data=SimpleNamespace(mime_type="image/png", data=raster()),
            )])

    provider = GeminiIllustrationProvider(SimpleNamespace(models=Models()), "image-test", 18)
    assert asyncio.run(provider.generate(request))
