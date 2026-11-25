import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
import httpx
from uuid import uuid4
from app.main import app

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


PRODUCTION_PROMPTS = (
    "Koji su najzanimljiviji kulturni događaji u Beogradu ovog vikenda?",
    "Pretraži internet i pronađi tri konkretna kulturna događaja u Beogradu za 28. i 29. novembar 2026. godine. Navedi naziv događaja, datum, lokaciju i link do izvora. Nemoj izmišljati podatke.",
)


@pytest.mark.parametrize("message", (
    *PRODUCTION_PROMPTS,
    "Који су концерти у Београду наредног викенда?",
    "Koje su izložbe sljedećeg vikenda?",
    "What exhibitions are on this weekend?",
    "Koje su izložbe 28. i 29. novembra?",
    "Претражи интернет за тај податак.",
    "Look up online how the policy changed.",
    "Koja je cijena zlata ovog mjeseca?",
    "daj mi prognozu za tri dana za Beograd",
    "Kakva je prognoza za sutra u Beogradu? Odgovori na italijanskom.",
    "Ko je trenutno predsednik Evropske komisije?",
    "Kush është presidenti aktual i Shqipërisë?",
))
def test_freshness_sensitive_messages_enable_grounding(message: str) -> None:
    assert decide_chat_grounding(message).enabled is True


@pytest.mark.parametrize("message", (
    "What is an AI agent?", "Objasni mi kako radi DNS.",
    "Napiši priču o koncertu večeras.", "Prevedi: pretraži internet.",
    "Izračunaj koliko je 42 + 5 danas.", "What if the market crashed tomorrow?",
    "I feel better today.",
))
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
    models = FakeModels([grounded_response("Domani a Belgrado...", [web_chunk("Source", "https://example.test/weather")])])
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
    assert result.summary != "Aktuelni odgovor."


@pytest.mark.parametrize("failure", [
    InvalidGroundingRequest("private provider details"), TimeoutError(),
    SimpleNamespace(parsed=None, text="{malformed"),
    grounded_response("Unsupported claim", [web_chunk("Bad", "https://[broken")]),
])
def test_grounding_failure_returns_safe_limitation_without_second_call(failure) -> None:
    models = FakeModels([failure])
    provider = GeminiProvider(settings(), FakeClient(models))
    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="Kakvo je vreme danas?"), enable_grounding=True,
    ))
    assert len(models.calls) == 1
    assert models.calls[0]["config"].tools[0].google_search is not None
    assert "couldn't verify" in result.summary or "potvrdim" in result.summary
    assert result.sources == []


def test_grounding_cancellation_propagates() -> None:
    models = FakeModels([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(GeminiProvider(settings(), FakeClient(models)).generate_chat_response(
            ChatRequest(message=PRODUCTION_PROMPTS[0]), enable_grounding=True,
        ))
    assert len(models.calls) == 1


@pytest.mark.parametrize("hype", [False, True])
def test_specialized_routes_take_precedence_over_explicit_search(hype):
    class Reader:
        async def retrieve(self, message):
            assert not hype
            return SimpleNamespace(documents=[object()])

    class Retriever:
        async def retrieve(self, message):
            assert hype
            return object()

    class Provider:
        async def generate_chat_response(self, request, **kwargs):
            return kwargs

    service = ChatService(provider=Provider(), retriever=Retriever(), source_reader=Reader())
    message = f"Pretraži internet za {'Hype TV' if hype else 'vesti'} https://example.test/"
    arguments = asyncio.run(service.generate_response(ChatRequest(message=message)))
    assert arguments["hype_context" if hype else "source_context"] is not None
    assert not arguments.get("enable_grounding")


@pytest.mark.parametrize("message", PRODUCTION_PROMPTS)
@pytest.mark.parametrize("provider_error", [False, True])
def test_production_prompts_reach_search_and_charge_once(monkeypatch, message, provider_error):
    outcome = InvalidGroundingRequest("private details") if provider_error else grounded_response(
        "Događaj", [web_chunk("Program", "https://example.test/program")],
    )
    models = FakeModels([outcome])
    provider = GeminiProvider(settings(), FakeClient(models))
    monkeypatch.setattr(ChatService, "_provider_from_settings", lambda self: provider)
    headers = {"X-Anonymous-ID": str(uuid4())}

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.post("/api/chat", headers=headers, json={"message": message})
            usage = await client.get("/api/usage", headers=headers)
            return result, usage

    result, usage = asyncio.run(send())
    assert result.status_code == 200
    assert usage.json()["used"] == 1
    assert len(models.calls) == 1
    assert models.calls[0]["config"].tools[0].google_search is not None
    assert bool(result.json()["sources"]) is not provider_error


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
    models = FakeModels([grounded_response("The current product is shown in the image.", [
        web_chunk("Product", "https://example.test/product"),
    ])])
    provider = GeminiProvider(settings(), FakeClient(models))
    result = asyncio.run(provider.generate_chat_response(
        ChatRequest(message="What is the current version of this product?"),
        images=[ImageAttachment(data=b"image", content_type="image/png")],
        enable_grounding=True,
    ))
    assert isinstance(models.calls[0]["contents"], list)
    assert models.calls[0]["config"].tools[0].google_search is not None
    assert result.answer_type == "chat"
