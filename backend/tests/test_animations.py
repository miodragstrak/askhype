import asyncio
import copy
import importlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.dependencies import (
    get_animation_provider, get_animation_repository, get_authenticated_identity,
    get_generative_svg_provider,
)
from app.auth.identity import RequestIdentity
from app.main import app
from app.providers.animation import (
    ACTION_ALIASES, ANIMATION_PLANNING_INSTRUCTION, CHARACTER_TYPE_ALIASES,
    GeminiAnimationProvider, MockAnimationProvider, normalize_animation_payload,
    prepare_gemini_animation_schema,
)
from app.providers.exceptions import AIAnimationPlanError, AIProviderRateLimitError, AIProviderUnavailableError
from app.repositories.animation_repository import AnimationLimitReached, InMemoryAnimationUsageRepository
from app.schemas.animations import AnimationPlan, AnimationRequest
from app.services.animation_generation import AnimationGenerationService
from app.core.config import settings
from app.renderers.cartoon_renderer import CartoonRenderTimeout, RenderArtifact, create_workspace
from app.renderers.svg_sanitizer import SvgValidationError
from app.schemas.generative_svg import ArtDirection, ReferenceArtAnalysis
from app.schemas.generative_svg import StoryboardPlan
animation_routes = importlib.import_module("app.api.routes.animations")


def _plan() -> AnimationPlan:
    return asyncio.run(MockAnimationProvider().generate_plan("Scena", "sr"))


def _identity() -> RequestIdentity:
    return RequestIdentity("authenticated", uuid4(), None, "free", "person@example.com")


_VALID_ENVELOPE = {"plan": _plan().model_dump()}


def test_strict_animation_plan_limits_and_targets():
    plan = _plan()
    assert plan.duration_seconds <= 15 and len(plan.characters) <= 3 and len(plan.timeline) <= 30
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate({**plan.model_dump(), "duration_seconds": 16})
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate({**plan.model_dump(), "characters": plan.model_dump()["characters"] * 2})
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate({**plan.model_dump(), "timeline": [{"start": 0, "duration": 1, "target_id": "child", "action": "wave"}] * 31})
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate({**plan.model_dump(), "timeline": [{"start": 0, "duration": 1, "target_id": "child", "action": "execute_code"}]})
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate({**plan.model_dump(), "timeline": [{"start": 0, "duration": 1, "target_id": "missing", "action": "wave"}]})
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate({**plan.model_dump(), "timeline": [{"start": 0, "duration": 1, "target_id": "child", "action": "speech", "parameters": {"text": "x" * 161}}]})


def test_gemini_animation_schema_is_code_free_and_sanitized():
    schema = prepare_gemini_animation_schema()
    serialized = str(schema)
    for keyword in ("discriminator", "const", "minLength", "maxLength", "minItems", "maxItems", "pattern", "exclusiveMinimum"):
        assert f"'{keyword}'" not in serialized
    assert "enter_left" in serialized and "speech" in serialized


def test_gemini_provider_validates_structured_plan():
    async def run():
        client = SimpleNamespace()
        provider = GeminiAnimationProvider(client=client)
        expected = await MockAnimationProvider().generate_plan("Scena", "sr")
        async def response(**kwargs):
            return SimpleNamespace(parsed={"plan": expected.model_dump()}, text="")
        provider._gemini._generate_content = response
        assert (await provider.generate_plan("Scena", "sr")).title
    asyncio.run(run())


def _envelope() -> dict:
    return copy.deepcopy(_VALID_ENVELOPE)


def test_obvious_character_and_action_aliases_are_normalized():
    payload = _envelope()
    payload["plan"]["characters"][0]["type"] = "woman"
    payload["plan"]["characters"][1]["type"] = "dog"
    payload["plan"]["timeline"][0]["action"] = "jump"
    normalized = normalize_animation_payload(payload)
    assert normalized["plan"]["characters"][0]["type"] == "person"
    assert normalized["plan"]["characters"][1]["type"] == "animal"
    assert normalized["plan"]["timeline"][0]["action"] == "bounce"
    assert CHARACTER_TYPE_ALIASES["girl"] == "child"
    assert ACTION_ALIASES["look_upward"] == "look_up"


def test_existing_valid_plan_is_unchanged_by_normalization():
    payload = _envelope()
    assert normalize_animation_payload(payload) == payload


def test_unknown_character_and_action_remain_rejected_after_normalization():
    payload = _envelope()
    payload["plan"]["characters"][0]["type"] = "wizard"
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate(normalize_animation_payload(payload)["plan"])
    payload = _envelope()
    payload["plan"]["timeline"][0]["action"] = "fly_around"
    with pytest.raises(ValidationError):
        AnimationPlan.model_validate(normalize_animation_payload(payload)["plan"])


def test_speech_without_grounded_text_is_omitted_not_invented():
    payload = _envelope()
    payload["plan"]["timeline"].append({
        "start": 1, "duration": 1, "target_id": "child", "action": "speech", "parameters": {},
    })
    normalized = normalize_animation_payload(payload)
    assert not any(event["action"] == "speech" for event in normalized["plan"]["timeline"])
    AnimationPlan.model_validate(normalized["plan"])


def test_serbian_natural_language_regression_maps_to_valid_controlled_plan():
    async def run():
        payload = _envelope()
        first, second = payload["plan"]["characters"]
        first.update(id="woman", name="Žena", type="woman")
        second.update(id="child", name="Dete", type="girl")
        dog = {**second, "id": "dog", "name": "Pas", "type": "dog"}
        payload["plan"]["characters"] = [first, second, dog]
        payload["plan"]["timeline"] = [
            {"start": 0, "duration": 2, "target_id": "woman", "action": "enter_left", "parameters": {}},
            {"start": 2, "duration": 2, "target_id": "woman", "action": "wave_hand", "parameters": {}},
            {"start": 2, "duration": 2, "target_id": "child", "action": "jump", "parameters": {}},
            {"start": 4, "duration": 2, "target_id": "dog", "action": "look_upward", "parameters": {}},
            {"start": 6, "duration": 1, "target_id": "child", "action": "speech", "parameters": {}},
        ]
        provider = GeminiAnimationProvider(client=SimpleNamespace())
        calls = []
        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return SimpleNamespace(parsed=payload, text="")
        provider._gemini._generate_content = response
        prompt = "Žena ulazi sa leve strane, maše detetu, dete poskoči od sreće, pas pogleda nagore, a onda se pojavi balon sa tekstom."
        plan = await provider.generate_plan(prompt, "sr")
        assert [item.type for item in plan.characters] == ["person", "child", "animal"]
        assert [event.action for event in plan.timeline] == ["enter_left", "wave", "bounce", "look_up"]
        assert len(calls) == 1
    asyncio.run(run())


def test_provider_instructions_enumerate_and_explain_controlled_mapping():
    assert "Allowed character types: person, child, robot, animal, creature" in ANIMATION_PLANNING_INSTRUCTION
    assert "woman/man/adult" in ANIMATION_PLANNING_INSTRUCTION
    assert "jump/hop/poskočiti to bounce" in ANIMATION_PLANNING_INSTRUCTION
    assert "Never invent action names or character types" in ANIMATION_PLANNING_INSTRUCTION


def test_one_repair_attempt_recovers_invalid_provider_plan():
    async def run():
        invalid = _envelope()
        invalid["plan"]["timeline"][0]["action"] = "leap"
        valid = _envelope()
        responses = [invalid, valid]
        provider = GeminiAnimationProvider(client=SimpleNamespace())
        calls = []
        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return SimpleNamespace(parsed=responses.pop(0), text="")
        provider._gemini._generate_content = response
        result = await provider.generate_plan("Scena", "sr")
        assert result.title and len(calls) == 2
        assert "Validation feedback" in calls[1]
        assert "literal_error" in calls[1]
    asyncio.run(run())


def test_repair_failure_stops_after_two_calls_and_exposes_no_raw_content(caplog):
    async def run():
        invalid = _envelope()
        invalid["plan"]["timeline"][0]["action"] = "secret-raw-provider-content"
        provider = GeminiAnimationProvider(client=SimpleNamespace())
        calls = 0
        async def response(**kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(parsed=invalid, text="")
        provider._gemini._generate_content = response
        with pytest.raises(AIAnimationPlanError, match="after repair") as captured:
            await provider.generate_plan("Scena", "sr")
        assert calls == 2
        assert "secret-raw-provider-content" not in str(captured.value)
    caplog.set_level("WARNING")
    asyncio.run(run())
    assert "secret-raw-provider-content" not in caplog.text


def test_failed_generation_does_not_consume_animation_quota():
    async def run():
        repository = InMemoryAnimationUsageRepository()
        owner = _identity()
        class Failing:
            provider_name = "gemini"; model = "test"
            async def generate_plan(self, prompt, language): raise AIProviderUnavailableError("private")
        with pytest.raises(AIProviderUnavailableError):
            await AnimationGenerationService(repository, Failing()).generate(SimpleNamespace(prompt="x", language="sr"), owner)
        assert next(iter(repository.events.values()))["status"] == "failed"
        result = await AnimationGenerationService(repository, MockAnimationProvider()).generate(SimpleNamespace(prompt="x", language="sr"), owner)
        assert result.quota.used == 1
    asyncio.run(run())


def test_animation_daily_quota_is_concurrency_safe_in_memory():
    async def run():
        repository = InMemoryAnimationUsageRepository()
        owner = _identity().user_id
        async def reserve():
            try:
                return await repository.reserve(event_id=uuid4(), user_id=owner, limit=1)
            except AnimationLimitReached:
                return None
        assert sum(item is not None for item in await asyncio.gather(reserve(), reserve())) == 1
    asyncio.run(run())


def test_animation_api_is_authenticated_and_returns_quota_metadata():
    repository = InMemoryAnimationUsageRepository()
    async def identity(): return _identity()
    async def repo(): return repository
    async def provider(): return MockAnimationProvider()
    app.dependency_overrides[get_authenticated_identity] = identity
    app.dependency_overrides[get_animation_repository] = repo
    app.dependency_overrides[get_animation_provider] = provider
    try:
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/api/animations/generate", json={"prompt": "Dečak i robot"})
        response = asyncio.run(request())
        assert response.status_code == 200
        assert response.json()["quota"]["remaining"] == 9
        assert response.json()["plan"]["characters"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(("error", "status", "code"), [
    (AIProviderRateLimitError("secret raw provider body"), 429, "provider_rate_limited"),
    (AIProviderUnavailableError("secret raw provider body"), 503, "provider_unavailable"),
])
def test_animation_api_maps_provider_errors_without_raw_details(error, status, code):
    repository = InMemoryAnimationUsageRepository()
    class FailingProvider:
        provider_name = "gemini"; model = "test"
        async def generate_plan(self, prompt, language): raise error
    async def identity(): return _identity()
    async def repo(): return repository
    async def provider(): return FailingProvider()
    app.dependency_overrides[get_authenticated_identity] = identity
    app.dependency_overrides[get_animation_repository] = repo
    app.dependency_overrides[get_animation_provider] = provider
    try:
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/api/animations/generate", json={"prompt": "Scena"})
        response = asyncio.run(request())
        assert response.status_code == status and response.json()["detail"]["code"] == code
        assert "secret raw" not in response.text
        assert next(iter(repository.events.values()))["status"] == "failed"
    finally:
        app.dependency_overrides.clear()


def test_mp4_poc_endpoint_is_disabled_by_default_and_streams_with_cleanup_when_enabled(monkeypatch):
    workspace = create_workspace()
    output = workspace / "output.mp4"
    output.write_bytes(b"safe-mp4")
    artifact = RenderArtifact(workspace, output, 25, 0.25, len(b"safe-mp4"))
    monkeypatch.setattr(animation_routes, "render_video", lambda plan: artifact)
    async def direct_threadpool(function, *args, **kwargs): return function(*args, **kwargs)
    monkeypatch.setattr(animation_routes, "run_in_threadpool", direct_threadpool)
    async def identity(): return _identity()
    async def provider(): return MockAnimationProvider()
    app.dependency_overrides[get_authenticated_identity] = identity
    app.dependency_overrides[get_animation_provider] = provider
    async def request():
        payload = AnimationRequest(prompt="Scena")
        with pytest.raises(HTTPException) as disabled:
            await animation_routes.render_animation_mp4(payload, await identity(), await provider())
        settings.animation_mp4_poc_enabled = True
        enabled = await animation_routes.render_animation_mp4(payload, await identity(), await provider())
        return disabled.value, enabled
    try:
        disabled, enabled = asyncio.run(request())
        assert disabled.status_code == 404
        assert Path(enabled.path).read_bytes() == b"safe-mp4"
        assert enabled.media_type == "video/mp4"
        assert enabled.headers["x-askhype-animation-resolution"] == "1280x720"
        assert enabled.background is not None
        animation_routes.cleanup_workspace(workspace)
        assert not workspace.exists()
    finally:
        if workspace.exists():
            animation_routes.cleanup_workspace(workspace)
        settings.animation_mp4_poc_enabled = False
        app.dependency_overrides.clear()


def test_mp4_poc_maps_render_timeout_without_internal_details(monkeypatch):
    def timeout(plan): raise CartoonRenderTimeout("private filesystem details")
    async def direct_threadpool(function, *args, **kwargs): return function(*args, **kwargs)
    monkeypatch.setattr(animation_routes, "render_video", timeout)
    monkeypatch.setattr(animation_routes, "run_in_threadpool", direct_threadpool)
    settings.animation_mp4_poc_enabled = True
    try:
        with pytest.raises(HTTPException) as captured:
            asyncio.run(animation_routes.render_animation_mp4(
                AnimationRequest(prompt="Scena"), _identity(), MockAnimationProvider(),
            ))
        assert captured.value.status_code == 504
        assert captured.value.detail["code"] == "render_timeout"
        assert "private filesystem" not in str(captured.value.detail)
    finally:
        settings.animation_mp4_poc_enabled = False


class _GenerativeProvider:
    def __init__(self, failure=None): self.failure = failure
    async def generate(self, prompt, reference_image=None):
        raise AssertionError("beta service must not request provider-generated SVG")
    async def generate_art_direction(self, prompt):
        if self.failure: raise self.failure
        return _glow_direction()
    async def generate_storyboard(self, prompt, duration_seconds):
        if self.failure: raise self.failure
        from app.schemas.generative_svg import StoryboardPlan
        durations = [duration_seconds // 3, duration_seconds // 3, duration_seconds - 2 * (duration_seconds // 3)]
        return StoryboardPlan.model_validate({
            "title": "Priča", "total_duration_seconds": duration_seconds,
            "shared_art_direction": _glow_direction().model_dump(),
            "recurring_subjects": [{"id": "girl", "name": "Devojčica", "kind": "child", "appearance": "zaobljen lik"}],
            "scenes": [{"id": f"scene_{index + 1}", "duration_seconds": value, "description": "Devojčica gleda zvezde", "environment": "Noćno nebo", "subject_ids": ["girl"], "action": "Blago lebdenje", "mood": "Sanjivo", "composition": "Lik u centru", "transition_in": "fade", "transition_out": "crossfade"} for index, value in enumerate(durations)],
        })
    async def analyze_reference(self, reference_image):
        return ReferenceArtAnalysis(
            dominant_palette=["#112233", "#445566"], contrast_level="soft",
            lighting_style="glow", shape_language="round", line_treatment="thin",
            texture_feel="smooth", depth_style="layered", composition_tendency="centered",
            mood="dreamy", softness="soft", visual_complexity="medium",
            background_character="atmospheric", character_style_notes="rounded",
            motion_style_suggestion="slow", confidence_notes="high",
        )


def _glow_direction() -> ArtDirection:
    return ArtDirection.model_validate({
        "title": "Devojčica i pas", "duration_seconds": 10,
        "scene_description": "Devojčica i pas gledaju zvezde.",
        "characters": [
            {"name": "Devojčica", "role": "posmatrač", "appearance": "zaobljen lik"},
            {"name": "Pas", "role": "pratilac", "appearance": "mali pas"},
        ],
        "objects": [], "background_description": "Noćno zvezdano nebo",
        "composition": "Dva lika u centru", "visual_style": "Meki glow",
        "shape_language": "Zaobljeno", "palette": ["#112233", "#445566", "#ffd166"],
        "lighting": "Mesečev sjaj", "line_treatment": "Meke linije", "depth_style": "Slojevito",
        "mood": "Sanjivo", "motion_style": "Blago lebdenje",
        "timeline_beats": [{"start": 0, "duration": 10, "description": "Posmatranje", "motion": "Lebdenje"}],
    })


def _storyboard(scene_count=3, total=15):
    durations = [total // scene_count] * scene_count
    durations[-1] += total - sum(durations)
    return {
        "title": "Putovanje", "total_duration_seconds": total,
        "shared_art_direction": _glow_direction().model_dump(),
        "recurring_subjects": [{"id": "hero", "name": "Plavo biće", "kind": "creature", "appearance": "Meko plavo biće sa zlatnim sjajem"}],
        "scenes": [{"id": f"scene_{index + 1}", "duration_seconds": duration, "description": f"Scena {index + 1}", "environment": "Svemir", "subject_ids": ["hero"], "action": "Blago leti", "mood": "Sanjivo", "composition": "Heroj u srednjem planu", "transition_in": "fade", "transition_out": "crossfade"} for index, duration in enumerate(durations)],
    }


def test_storyboard_accepts_three_and_six_scenes_with_exact_duration():
    assert len(StoryboardPlan.model_validate(_storyboard(3, 15)).scenes) == 3
    assert len(StoryboardPlan.model_validate(_storyboard(6, 30)).scenes) == 6


def test_storyboard_rejects_duration_mismatch_and_unknown_subject():
    from pydantic import ValidationError
    mismatch = _storyboard(); mismatch["total_duration_seconds"] = 20
    with pytest.raises(ValidationError, match="scene durations"):
        StoryboardPlan.model_validate(mismatch)
    unknown = _storyboard(); unknown["scenes"][0]["subject_ids"] = ["missing"]
    with pytest.raises(ValidationError, match="unknown recurring subject"):
        StoryboardPlan.model_validate(unknown)


def _generative_request(files=None, data=None, authenticated=True):
    repository = InMemoryAnimationUsageRepository()
    async def identity(): return _identity()
    async def repo(): return repository
    async def provider(): return _GenerativeProvider()
    app.dependency_overrides[get_animation_repository] = repo
    app.dependency_overrides[get_generative_svg_provider] = provider
    if authenticated: app.dependency_overrides[get_authenticated_identity] = identity
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/animations/generative-svg", data=data or {"prompt": "Noćna scena"}, files=files)
    try: return asyncio.run(request()), repository
    finally: app.dependency_overrides.clear()


def test_generative_svg_beta_is_disabled_by_default_and_requires_authentication():
    response, _ = _generative_request()
    assert response.status_code == 404 and response.json()["detail"]["code"] == "feature_disabled"
    settings.generative_svg_beta_enabled = True
    response, _ = _generative_request(authenticated=False)
    assert response.status_code == 401


def test_generative_svg_prompt_only_and_reference_upload():
    settings.generative_svg_beta_enabled = True
    response, _ = _generative_request()
    assert response.status_code == 200
    assert len(response.json()["scenes"]) == 3 and response.json()["scenes"][0]["svg"].startswith("<svg")
    from io import BytesIO
    from PIL import Image
    image = BytesIO(); Image.new("RGB", (8, 8), "navy").save(image, format="PNG")
    response, _ = _generative_request(files={"reference_image": ("style.png", image.getvalue(), "image/png")})
    assert response.status_code == 200 and len(response.json()["scenes"]) == 3


def test_generative_svg_rejects_invalid_reference_before_quota():
    settings.generative_svg_beta_enabled = True
    response, repository = _generative_request(files={"reference_image": ("bad.png", b"bad", "image/png")})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "invalid_reference_image"
    assert repository.events == {}


def test_generative_svg_safe_failure_releases_quota_and_hides_details():
    settings.generative_svg_beta_enabled = True
    repository = InMemoryAnimationUsageRepository()
    async def identity(): return _identity()
    async def repo(): return repository
    async def provider(): return _GenerativeProvider(SvgValidationError("invalid_xml", "private raw svg"))
    app.dependency_overrides.update({get_authenticated_identity: identity, get_animation_repository: repo, get_generative_svg_provider: provider})
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/animations/generative-svg", data={"prompt": "Scena"})
    try:
        response = asyncio.run(request())
        assert response.status_code == 502 and response.json()["detail"]["code"] == "invalid_animation_artifact"
        assert "private raw" not in response.text
        assert next(iter(repository.events.values()))["status"] == "failed"
    finally: app.dependency_overrides.clear()


def test_generative_svg_quality_failure_keeps_safe_ui_error_and_persists_category():
    settings.generative_svg_beta_enabled = True
    repository = InMemoryAnimationUsageRepository()
    async def identity(): return _identity()
    async def repo(): return repository
    async def provider(): return _GenerativeProvider(SvgValidationError("artifact_quality_failed", "private coordinates"))
    app.dependency_overrides.update({get_authenticated_identity: identity, get_animation_repository: repo, get_generative_svg_provider: provider})
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/animations/generative-svg", data={"prompt": "Scena"})
    try:
        response = asyncio.run(request())
        event = next(iter(repository.events.values()))
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "invalid_animation_artifact"
        assert "private coordinates" not in response.text
        assert event["failure_category"] == "artifact_quality_failed"
    finally: app.dependency_overrides.clear()


def test_generative_svg_timeout_keeps_timeout_response_and_persists_category():
    settings.generative_svg_beta_enabled = True
    repository = InMemoryAnimationUsageRepository()
    async def identity(): return _identity()
    async def repo(): return repository
    async def provider(): return _GenerativeProvider(TimeoutError())
    app.dependency_overrides.update({get_authenticated_identity: identity, get_animation_repository: repo, get_generative_svg_provider: provider})
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/animations/generative-svg", data={"prompt": "Scena"})
    try:
        response = asyncio.run(request())
        event = next(iter(repository.events.values()))
        assert response.status_code == 504
        assert response.json()["detail"]["code"] == "provider_timeout"
        assert event["failure_category"] == "provider_timeout"
    finally: app.dependency_overrides.clear()


def test_generative_svg_uses_existing_animation_daily_quota():
    settings.generative_svg_beta_enabled = True
    settings.animation_daily_limit = 1
    repository = InMemoryAnimationUsageRepository()
    owner = _identity()
    async def identity(): return owner
    async def repo(): return repository
    async def provider(): return _GenerativeProvider()
    app.dependency_overrides.update({get_authenticated_identity: identity, get_animation_repository: repo, get_generative_svg_provider: provider})
    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/api/animations/generative-svg", data={"prompt": "Prva"})
            second = await client.post("/api/animations/generative-svg", data={"prompt": "Druga"})
            return first, second
    try:
        first, second = asyncio.run(requests())
        assert first.status_code == 200 and first.json()["remaining_quota"] == 0
        assert second.status_code == 429 and second.json()["detail"]["code"] == "animation_daily_quota_reached"
    finally: app.dependency_overrides.clear()
