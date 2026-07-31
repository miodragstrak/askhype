import asyncio
import copy
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from google import genai
from google.genai import types
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic import TypeAdapter

from app.core.config import Settings, settings
from app.prompts.askhype import ASKHYPE_SYSTEM_INSTRUCTION
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.schemas.chat import ChatRequest, ChatResponse, Recommendation, SourceReference
from app.services.location_context import build_location_context

logger = logging.getLogger(__name__)

_URL_ADAPTER = TypeAdapter(AnyUrl)
_UNSUPPORTED_GEMINI_SCHEMA_KEYS = frozenset({"default"})


class GeminiRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    category: str
    short_description: str
    location: str
    estimated_price: str | None = None
    date_or_duration: str | None = None
    reason: str
    image_url: str | None = None
    source_url: str | None = None

    @field_validator(
        "id",
        "title",
        "category",
        "short_description",
        "location",
        "reason",
        mode="before",
    )
    @classmethod
    def _trim_required_string(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @field_validator(
        "estimated_price",
        "date_or_duration",
        "image_url",
        "source_url",
        mode="before",
    )
    @classmethod
    def _trim_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("must be a string or null")
        trimmed = value.strip()
        return trimmed or None


class GeminiSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str | None = None
    last_verified: datetime | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _trim_title(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @field_validator("url", mode="before")
    @classmethod
    def _trim_url(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("must be a string or null")
        trimmed = value.strip()
        return trimmed or None

    @field_validator("last_verified")
    @classmethod
    def _require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("must be timezone-aware")
        return value


class GeminiChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_type: str
    summary: str
    recommendations: list[GeminiRecommendation] = Field(min_length=3, max_length=3)
    follow_up_actions: list[str] = Field(min_length=2, max_length=4)
    sources: list[GeminiSourceReference] = Field(default_factory=list)

    @field_validator("answer_type", "summary", mode="before")
    @classmethod
    def _trim_required_string(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @field_validator("follow_up_actions", mode="before")
    @classmethod
    def _normalize_actions(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("must be a list")

        seen: set[str] = set()
        actions: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("must contain only strings")
            action = item.strip()
            if not action:
                continue
            key = action.casefold()
            if key not in seen:
                seen.add(key)
                actions.append(action)

        if not 2 <= len(actions) <= 4:
            raise ValueError("must contain 2 to 4 non-empty unique actions")
        return actions


class GeminiProvider:
    provider_name = "gemini"

    def __init__(
        self,
        app_settings: Settings = settings,
        client: Any | None = None,
    ) -> None:
        self.settings = app_settings
        self.model = app_settings.gemini_model
        self._client = client or self._build_client(app_settings)

    async def generate_chat_response(self, request: ChatRequest) -> ChatResponse:
        user_context = self._build_user_context(request)

        try:
            config = self._build_generation_config()
            async with asyncio.timeout(self.settings.gemini_timeout_seconds):
                response = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=user_context,
                    config=config,
                )
        except TimeoutError as exc:
            self._log_provider_failure("timeout")
            raise AIProviderTimeoutError("Gemini provider timed out.") from exc
        except asyncio.CancelledError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            self._log_provider_failure("invalid_request_schema", exc)
            raise AIProviderResponseError("Gemini structured output schema is invalid.") from exc
        except Exception as exc:
            if self._is_invalid_request_schema_error(exc):
                self._log_provider_failure("invalid_request_schema", exc)
                raise AIProviderResponseError("Gemini request schema was rejected.") from exc
            self._log_provider_failure("unavailable", exc)
            raise AIProviderUnavailableError("Gemini provider is unavailable.") from exc

        payload = self._parse_payload(response)
        return self._to_chat_response(request, payload)

    def _build_client(self, app_settings: Settings) -> genai.Client:
        if app_settings.gemini_api_key is None:
            raise AIProviderConfigurationError("Gemini provider is not configured.")

        api_key = app_settings.gemini_api_key.get_secret_value()
        if not api_key.strip():
            raise AIProviderConfigurationError("Gemini provider is not configured.")

        return genai.Client(api_key=api_key)

    def _build_generation_config(self) -> types.GenerateContentConfig:
        response_schema = prepare_gemini_response_schema(GeminiChatPayload.model_json_schema())
        return types.GenerateContentConfig(
            system_instruction=ASKHYPE_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=response_schema,
            temperature=self.settings.gemini_temperature,
            max_output_tokens=self.settings.gemini_max_output_tokens,
        )

    def _is_invalid_request_schema_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status_code != 400:
            return False

        text = " ".join(
            str(part)
            for part in [
                getattr(exc, "message", None),
                getattr(exc, "status", None),
                exc,
            ]
            if part is not None
        ).casefold()
        return "invalid_argument" in text or "schema" in text

    def _parse_payload(self, response: Any) -> GeminiChatPayload:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, GeminiChatPayload):
            return parsed
        if isinstance(parsed, dict):
            try:
                return GeminiChatPayload.model_validate(parsed)
            except ValidationError as exc:
                self._log_provider_failure("invalid_response", exc)
                raise AIProviderResponseError("Gemini returned an invalid response.") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            self._log_provider_failure("invalid_response")
            raise AIProviderResponseError("Gemini returned an invalid response.")

        try:
            return GeminiChatPayload.model_validate_json(text)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            self._log_provider_failure("invalid_response", exc)
            raise AIProviderResponseError("Gemini returned an invalid response.") from exc

    def _to_chat_response(
        self,
        request: ChatRequest,
        payload: GeminiChatPayload,
    ) -> ChatResponse:
        return ChatResponse(
            conversation_id=request.conversation_id or f"conv_{uuid4()}",
            provider=self.provider_name,
            answer_type=payload.answer_type,
            summary=payload.summary,
            recommendations=[
                Recommendation(
                    id=item.id,
                    title=item.title,
                    category=item.category,
                    short_description=item.short_description,
                    location=item.location,
                    estimated_price=item.estimated_price,
                    date_or_duration=item.date_or_duration,
                    reason=item.reason,
                    image_url=self._valid_url_or_none(item.image_url),
                    source_url=None,
                )
                for item in payload.recommendations
            ],
            follow_up_actions=payload.follow_up_actions,
            sources=[
                SourceReference(
                    title=item.title,
                    url=None,
                    last_verified=item.last_verified,
                )
                for item in payload.sources
            ],
            generated_at=datetime.now(UTC),
        )

    def _build_user_context(self, request: ChatRequest) -> str:
        interests = ", ".join(request.interests) if request.interests else "none supplied"
        conversation = request.conversation_id or "none supplied"
        return "\n".join(
            [
                "AskHype chat request context:",
                f"message: {request.message}",
                "Location context:",
                build_location_context(request),
                f"language: {request.language}",
                f"interests: {interests}",
                f"conversation_id: {conversation}",
                "conversation_history: not available; the backend only passes the current request.",
            ]
        )

    def _valid_url_or_none(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(_URL_ADAPTER.validate_python(value))
        except ValidationError:
            return None

    def _log_provider_failure(
        self,
        category: str,
        exc: Exception | None = None,
    ) -> None:
        diagnostic = {
            "provider": self.provider_name,
            "category": category,
            "model": self.model,
        }
        if exc is None:
            logger.warning("AI provider failure: %s", diagnostic)
        else:
            logger.warning("AI provider failure: %s", diagnostic, exc_info=True)


def prepare_gemini_response_schema(schema: object) -> object:
    expanded = _inline_local_schema_refs(schema)
    sanitized = sanitize_gemini_schema(expanded)
    validate_schema_required_properties(sanitized)
    return sanitized


def sanitize_gemini_schema(value: object, *, inside_properties: bool = False) -> object:
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            if not inside_properties and key in _UNSUPPORTED_GEMINI_SCHEMA_KEYS:
                continue
            sanitized[key] = sanitize_gemini_schema(
                item,
                inside_properties=key == "properties",
            )
        return sanitized
    if isinstance(value, list):
        return [sanitize_gemini_schema(item, inside_properties=inside_properties) for item in value]
    return value


def validate_schema_required_properties(schema: object, *, path: str = "$") -> None:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        required = schema.get("required")
        if isinstance(properties, dict) and isinstance(required, list):
            missing = [
                item
                for item in required
                if isinstance(item, str) and item not in properties
            ]
            if missing:
                fields = ", ".join(sorted(missing))
                raise ValueError(f"Schema required fields missing at {path}: {fields}")

        for key, item in schema.items():
            validate_schema_required_properties(item, path=f"{path}.{key}")
    elif isinstance(schema, list):
        for index, item in enumerate(schema):
            validate_schema_required_properties(item, path=f"{path}[{index}]")


def _inline_local_schema_refs(schema: object) -> object:
    cloned = copy.deepcopy(schema)
    if not isinstance(cloned, dict):
        return cloned

    definitions = cloned.get("$defs")
    if not isinstance(definitions, dict):
        return cloned

    return _replace_local_refs(cloned, definitions)


def _replace_local_refs(value: object, definitions: dict[str, object]) -> object:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.removeprefix("#/$defs/")
            target = definitions.get(name)
            if target is None:
                return copy.deepcopy(value)
            return _replace_local_refs(copy.deepcopy(target), definitions)

        return {
            key: _replace_local_refs(item, definitions)
            for key, item in value.items()
            if key != "$defs"
        }
    if isinstance(value, list):
        return [_replace_local_refs(item, definitions) for item in value]
    return value
