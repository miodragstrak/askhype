import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.providers.gemini import GeminiProvider
from app.schemas.attachments import ImageAttachment
from app.schemas.chat import ChatRequest
from app.services.chat_grounding import decide_chat_grounding
from app.services.chat_service import ChatService


class FakeModels:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.aio = SimpleNamespace(models=models)


class InvalidGroundingRequest(Exception):
    status_code = 400
    status = "INVALID_ARGUMENT"


def settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="gemini",
        gemini_api_key="test-key",
        gemini_model="gemini-test-model",
        gemini_timeout_seconds=5,
    )


def grounded_response(answer: str, chunks: list[Any] | None = None) -> Any:
    metadata = SimpleNamespace(grounding_chunks=chunks) if chunks is not None else None
    return SimpleNamespace(
        parsed={"answer": answer},
        text=None,
        candidates=[SimpleNamespace(grounding_metadata=metadata)],
    )


def web_chunk(title: str | None, url: str | None) -> Any:
    return SimpleNamespace(web=SimpleNamespace(title=title, uri=url))


@pytest.mark.parametrize("message", (
    "daj mi prognozu za tri dana za Beograd",
    "Kakva je prognoza za sutra u Beogradu? Odgovori na italijanskom.",
    "Ko je trenutno predsednik Evropske komisije?",
    "Kush është presidenti aktual i Shqipërisë?",
))
def test_freshness_sensitive_messages_enable_grounding(message: str) -> None:
    assert decide_chat_grounding(message).enabled is True


@pytest.mark.parametrize("message", ("What is an AI agent?", "Objasni mi kako radi DNS."))
def test_evergreen_messages_disable_grounding(message: str) -> None:
    assert decide_chat_grounding(message).enabled is False


def test_serbian_weather_uses_google_search_and_maps_deduplicated_sources() -> None:
    chunks = [
        web_chunk("Vremenska prognoza", "https://weather.example/forecast"),
        web_chunk("Duplikat", "https://weather.example/forecast"),
        web_chunk("Meteorološki zavod", "https://meteo.example/beograd"),
        web_chunk("Unsafe", "javascript:alert(1)"),
    ]
    models = FakeModels([grounded_response("Prognoza za naredna tri dana je...", chunks)])
    provider = GeminiProvider(settings(), FakeClient(models))

    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="daj mi prognozu za tri dana za Beograd"),
        enable_grounding=True,
    ))

    assert result.answer_type == "chat"
    assert result.summary.startswith("Prognoza")
    assert result.recommendations == result.follow_up_actions == []
    assert [(source.title, source.url) for source in result.sources] == [
        ("Vremenska prognoza", "https://weather.example/forecast"),
        ("Meteorološki zavod", "https://meteo.example/beograd"),
    ]
    tool = models.calls[0]["config"].tools[0]
    assert tool.google_search is not None


def test_grounding_preserves_explicit_italian_language_rule() -> None:
    models = FakeModels([grounded_response("Domani a Belgrado...", [])])
    provider = GeminiProvider(settings(), FakeClient(models))
    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="Kakva je prognoza za sutra u Beogradu? Odgovori na italijanskom."),
        enable_grounding=True,
    ))
    combined = models.calls[0]["contents"] + models.calls[0]["config"].system_instruction
    assert "resolved_output_language: Italian (source: explicit_request)" in combined
    assert result.summary.startswith("Domani")


def test_missing_grounding_metadata_does_not_fabricate_sources() -> None:
    models = FakeModels([grounded_response("Aktuelni odgovor.")])
    provider = GeminiProvider(settings(), FakeClient(models))
    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="Šta je trenutno aktuelno?"), enable_grounding=True,
    ))
    assert result.sources == []


def test_grounding_failure_retries_without_search_and_requires_unverified_answer() -> None:
    models = FakeModels([
        InvalidGroundingRequest("search tool unavailable"),
        grounded_response("Ne mogu trenutno da proverim podatke uživo.", []),
    ])
    provider = GeminiProvider(settings(), FakeClient(models))
    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="Kakvo je vreme danas?"), enable_grounding=True,
    ))
    assert len(models.calls) == 2
    assert models.calls[0]["config"].tools[0].google_search is not None
    assert models.calls[1]["config"].tools is None
    assert "Live search could not be used" in models.calls[1]["config"].system_instruction
    assert result.summary.startswith("Ne mogu")
    assert result.sources == []


def test_chat_service_passes_grounding_only_for_fresh_ordinary_chat() -> None:
    captured: list[bool] = []

    class Provider:
        provider_name = "test"

        async def generate_chat_response(self, request, **kwargs):
            captured.append(kwargs.get("enable_grounding", False))
            return grounded_response("ok")

    class NoSource:
        async def retrieve(self, _message):
            return None

    service = ChatService(provider=Provider(), source_reader=NoSource())
    asyncio.run(service.generate_response(ChatRequest(message="What is an AI agent?")))
    asyncio.run(service.generate_response(ChatRequest(message="What is the weather today?")))
    assert captured == [False, True]


def test_image_chat_keeps_natural_grounded_request_contract() -> None:
    models = FakeModels([grounded_response("The current product is shown in the image.", [])])
    provider = GeminiProvider(settings(), FakeClient(models))
    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="What is the current version of this product?"),
        images=[ImageAttachment(data=b"image", content_type="image/png")],
        enable_grounding=True,
    ))
    assert isinstance(models.calls[0]["contents"], list)
    assert models.calls[0]["config"].tools[0].google_search is not None
    assert result.answer_type == "chat"
