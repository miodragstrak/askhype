import asyncio
import copy
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.api.dependencies import get_animation_provider, get_animation_repository, get_authenticated_identity
from app.auth.identity import RequestIdentity
from app.main import app
from app.providers.animation import (
    ACTION_ALIASES, ANIMATION_PLANNING_INSTRUCTION, CHARACTER_TYPE_ALIASES,
    GeminiAnimationProvider, MockAnimationProvider, normalize_animation_payload,
    prepare_gemini_animation_schema,
)
from app.providers.exceptions import AIAnimationPlanError, AIProviderRateLimitError, AIProviderUnavailableError
from app.repositories.animation_repository import AnimationLimitReached, InMemoryAnimationUsageRepository
from app.schemas.animations import AnimationPlan
from app.services.animation_generation import AnimationGenerationService


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
