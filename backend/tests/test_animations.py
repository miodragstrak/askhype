import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.api.dependencies import get_animation_provider, get_animation_repository, get_authenticated_identity
from app.auth.identity import RequestIdentity
from app.main import app
from app.providers.animation import GeminiAnimationProvider, MockAnimationProvider, prepare_gemini_animation_schema
from app.providers.exceptions import AIProviderRateLimitError, AIProviderUnavailableError
from app.repositories.animation_repository import AnimationLimitReached, InMemoryAnimationUsageRepository
from app.schemas.animations import AnimationPlan
from app.services.animation_generation import AnimationGenerationService


def _plan() -> AnimationPlan:
    return asyncio.run(MockAnimationProvider().generate_plan("Scena", "sr"))


def _identity() -> RequestIdentity:
    return RequestIdentity("authenticated", uuid4(), None, "free", "person@example.com")


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
