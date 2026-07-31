import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.providers.gemini import (
    GeminiChatPayload,
    GeminiProvider,
    prepare_gemini_response_schema,
    sanitize_gemini_schema,
    validate_schema_required_properties,
)
from app.schemas.chat import ChatRequest


class FakeResponse:
    def __init__(self, text: str | None = None, parsed: Any | None = None) -> None:
        self.text = text
        self.parsed = parsed


class FakeModels:
    def __init__(self, response: FakeResponse | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


class FakeAio:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.aio = FakeAio(models)


class FakeSdkError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.status = "INVALID_ARGUMENT"


def test_successful_structured_response_becomes_chat_response() -> None:
    models = FakeModels(FakeResponse(text=json.dumps(_valid_payload())))
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))
    request = ChatRequest(
        message="Predloži vikend izlazak u Beogradu",
        conversation_id="conv_existing",
        location="Beograd",
        language="sr",
        interests=["muzika", "hrana"],
    )

    response = asyncio.run(provider.generate_chat_response(request))

    assert response.provider == "gemini"
    assert response.conversation_id == "conv_existing"
    assert response.generated_at.tzinfo is not None
    assert response.generated_at.utcoffset() is not None
    assert len(response.recommendations) == 3
    assert response.recommendations[0].title == "Jazz veče"
    assert response.recommendations[0].source_url is None
    assert response.sources[0].url is None
    assert response.sources[0].last_verified is not None

    call = models.calls[0]
    assert call["model"] == "gemini-test-model"
    assert "Predloži vikend izlazak u Beogradu" in call["contents"]
    assert "Selected application location: Beograd" in call["contents"]
    assert "Any explicit place named in the current user message overrides" in call["contents"]
    assert "language: sr" in call["contents"]
    assert "interests: muzika, hrana" in call["contents"]
    assert "conversation_id: conv_existing" in call["contents"]
    assert "conversation_history: not available" in call["contents"]
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is None
    assert call["config"].response_json_schema is not None


def test_uuid_conversation_id_is_generated_when_absent() -> None:
    models = FakeModels(FakeResponse(text=json.dumps(_valid_payload())))
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))

    response = asyncio.run(
        provider.generate_chat_response(ChatRequest(message="Hrana u Novom Sadu"))
    )

    assert response.conversation_id.startswith("conv_")
    assert len(response.conversation_id) > len("conv_")


def test_missing_gemini_api_key_raises_configuration_error() -> None:
    app_settings = Settings(
        _env_file=None,
        ai_provider="gemini",
        gemini_api_key=None,
    )

    with pytest.raises(AIProviderConfigurationError) as exc_info:
        GeminiProvider(app_settings=app_settings)

    assert "key" not in str(exc_info.value).casefold()


def test_invalid_structured_json_is_rejected() -> None:
    models = FakeModels(FakeResponse(text="{not json"))
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))

    with pytest.raises(AIProviderResponseError):
        asyncio.run(provider.generate_chat_response(ChatRequest(message="Plan")))


def test_wrong_recommendation_count_is_rejected() -> None:
    payload = _valid_payload()
    payload["recommendations"] = payload["recommendations"][:2]
    models = FakeModels(FakeResponse(text=json.dumps(payload)))
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))

    with pytest.raises(AIProviderResponseError):
        asyncio.run(provider.generate_chat_response(ChatRequest(message="Plan")))


def test_generation_config_uses_sanitized_json_schema() -> None:
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(FakeModels(FakeResponse(text="{}"))))

    config = provider._build_generation_config()
    schema = config.response_json_schema

    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert schema is not None
    assert _find_key(schema, "default") == []
    assert schema["title"] == "GeminiChatPayload"
    assert schema["properties"]["recommendations"]["items"]["properties"]["title"]["type"] == "string"
    assert schema["properties"]["sources"]["items"]["properties"]["title"]["type"] == "string"
    validate_schema_required_properties(schema)


def test_schema_sanitizer_preserves_property_names_without_mutation() -> None:
    original = GeminiChatPayload.model_json_schema()
    sanitized = sanitize_gemini_schema(original)

    assert original["additionalProperties"] is False
    assert original["title"] == "GeminiChatPayload"
    assert original["$defs"]["GeminiRecommendation"]["additionalProperties"] is False
    assert original["$defs"]["GeminiSourceReference"]["additionalProperties"] is False
    assert sanitized["additionalProperties"] is False
    assert sanitized["title"] == "GeminiChatPayload"
    assert sanitized["$defs"]["GeminiRecommendation"]["properties"]["title"]["type"] == "string"
    assert sanitized["$defs"]["GeminiSourceReference"]["properties"]["title"]["type"] == "string"
    assert _find_key(sanitized, "default") == []


def test_schema_sanitizer_preserves_metadata_named_application_fields() -> None:
    schema = {
        "type": "object",
        "title": "SyntheticPayload",
        "default": {},
        "properties": {
            "title": {"type": "string", "default": "removed"},
            "default": {"type": "string"},
            "additionalProperties": {"type": "string"},
        },
        "required": ["title", "default", "additionalProperties"],
    }

    sanitized = sanitize_gemini_schema(schema)

    assert sanitized["title"] == "SyntheticPayload"
    assert "default" not in sanitized
    assert "title" in sanitized["properties"]
    assert "default" in sanitized["properties"]
    assert "additionalProperties" in sanitized["properties"]
    assert "default" not in sanitized["properties"]["title"]
    assert sanitized["required"] == ["title", "default", "additionalProperties"]
    validate_schema_required_properties(sanitized)


def test_prepare_schema_inlines_refs_and_preserves_required_properties() -> None:
    schema = prepare_gemini_response_schema(GeminiChatPayload.model_json_schema())

    assert "$defs" not in schema
    assert schema["properties"]["recommendations"]["items"]["properties"]["title"]["type"] == "string"
    assert schema["properties"]["sources"]["items"]["properties"]["title"]["type"] == "string"
    assert _missing_required_properties(schema) == []


def test_required_properties_validation_fails_locally() -> None:
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary", "title"],
    }

    with pytest.raises(ValueError, match="missing"):
        validate_schema_required_properties(schema)


def test_local_schema_validation_error_is_not_unavailable() -> None:
    models = FakeModels(exc=ValueError("properties.recommendations.items.additionalProperties"))
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))

    with pytest.raises(AIProviderResponseError) as exc_info:
        asyncio.run(provider.generate_chat_response(ChatRequest(message="Plan")))

    assert not isinstance(exc_info.value, AIProviderUnavailableError)
    assert "additionalProperties" not in str(exc_info.value)


def test_gemini_invalid_argument_schema_error_is_not_unavailable() -> None:
    models = FakeModels(
        exc=FakeSdkError(
            "400 INVALID_ARGUMENT: schema at properties.recommendations.items requires unspecified property 'title'",
            status_code=400,
        )
    )
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))

    with pytest.raises(AIProviderResponseError) as exc_info:
        asyncio.run(provider.generate_chat_response(ChatRequest(message="Plan")))

    assert not isinstance(exc_info.value, AIProviderUnavailableError)
    assert "title" not in str(exc_info.value)


def test_timeout_is_mapped_to_provider_timeout() -> None:
    models = FakeModels(exc=TimeoutError("timed out"))
    provider = GeminiProvider(app_settings=_settings(), client=FakeClient(models))

    with pytest.raises(AIProviderTimeoutError):
        asyncio.run(provider.generate_chat_response(ChatRequest(message="Plan")))


def test_sdk_unavailable_error_is_sanitized() -> None:
    secret = "test-secret-key"
    models = FakeModels(exc=RuntimeError(f"rate limited for {secret}"))
    provider = GeminiProvider(app_settings=_settings(api_key=secret), client=FakeClient(models))

    with pytest.raises(AIProviderUnavailableError) as exc_info:
        asyncio.run(provider.generate_chat_response(ChatRequest(message="Plan")))

    assert secret not in str(exc_info.value)
    assert "rate limited" not in str(exc_info.value)


def test_ai_provider_mock_does_not_require_gemini_api_key() -> None:
    app_settings = Settings(
        _env_file=None,
        ai_provider="mock",
        gemini_api_key=None,
    )

    assert app_settings.ai_provider == "mock"
    assert app_settings.gemini_api_key is None


def _find_key(value: object, target: str, path: str = "$") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}"
            if key == target:
                matches.append(next_path)
            matches.extend(_find_key(item, target, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(_find_key(item, target, f"{path}[{index}]"))
    return matches


def _missing_required_properties(value: object) -> list[str]:
    missing: list[str] = []
    if isinstance(value, dict):
        properties = value.get("properties")
        required = value.get("required")
        if isinstance(properties, dict) and isinstance(required, list):
            missing.extend(
                item
                for item in required
                if isinstance(item, str) and item not in properties
            )
        for item in value.values():
            missing.extend(_missing_required_properties(item))
    elif isinstance(value, list):
        for item in value:
            missing.extend(_missing_required_properties(item))
    return missing


def _settings(api_key: str = "test-secret-key") -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="gemini",
        gemini_api_key=api_key,
        gemini_model="gemini-test-model",
        gemini_timeout_seconds=45,
        gemini_temperature=0.3,
        gemini_max_output_tokens=1024,
    )


def _valid_payload() -> dict[str, Any]:
    return {
        "answer_type": "recommendations",
        "summary": "Tri praktične opcije. Aktualne detalje proveriti pre posete.",
        "recommendations": [
            {
                "id": "night-1",
                "title": " Jazz veče ",
                "category": "muzika",
                "short_description": "Manji klupski format sa živom muzikom.",
                "location": "Beograd",
                "estimated_price": "okvirno srednji budžet",
                "date_or_duration": "veče",
                "reason": "Odgovara interesovanju za muziku i opušten izlazak.",
                "image_url": None,
                "source_url": "https://example.com/untrusted-model-url",
            },
            {
                "id": "food-2",
                "title": "Lokalna večera",
                "category": "hrana",
                "short_description": "Mesto za večeru pre izlaska.",
                "location": "Beograd",
                "estimated_price": None,
                "date_or_duration": "60-90 minuta",
                "reason": "Dobar spoj hrane i lokacije za nastavak večeri.",
                "image_url": None,
                "source_url": None,
            },
            {
                "id": "walk-3",
                "title": "Šetnja kroz centar",
                "category": "kultura",
                "short_description": "Kratka kulturna pauza pre glavnog plana.",
                "location": "Beograd",
                "estimated_price": "besplatno",
                "date_or_duration": "45 minuta",
                "reason": "Dodaje mirniji deo večeri bez komplikovane logistike.",
                "image_url": None,
                "source_url": None,
            },
        ],
        "follow_up_actions": [
            "Napravi plan po satima",
            "Dodaj mirnije opcije",
            "Napravi plan po satima",
            "Predloži budžetsku verziju",
        ],
        "sources": [
            {
                "title": "AskHype opšte znanje - nije provereno uživo",
                "url": "https://example.com/untrusted-source-url",
                "last_verified": datetime(2026, 1, 1, 10, 0, tzinfo=UTC).isoformat(),
            }
        ],
    }
