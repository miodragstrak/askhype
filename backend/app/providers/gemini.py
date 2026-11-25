import asyncio
import copy
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import uuid4
from urllib.parse import urlsplit

from google import genai
from google.genai import types
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic import TypeAdapter

from app.core.config import Settings, settings
from app.prompts.askhype import ASKHYPE_SYSTEM_INSTRUCTION, DOCUMENT_ANALYSIS_INSTRUCTION, HYPE_GROUNDING_INSTRUCTION, IMAGE_ANALYSIS_INSTRUCTION, NATURAL_CHAT_INSTRUCTION, PRESENTATION_PLANNING_INSTRUCTION, SOURCE_ANALYSIS_INSTRUCTION, XLSX_TRANSFORMATION_PLANNING_INSTRUCTION
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AITransformationPlanError,
    AIPresentationPlanError,
)
from app.schemas.chat import ChatRequest, ChatResponse, Recommendation, SourceReference
from app.schemas.attachments import ImageAttachment
from app.schemas.documents import ExtractedDocument
from app.schemas.xlsx_transform import TransformationPlan, TransformationPlanEnvelope
from app.schemas.presentations import (
    BulletsSlide,
    ConclusionSlide,
    KeyMetricsSlide,
    MetricCard,
    PresentationPlan,
    SectionSlide,
    TableSlide,
    TitleSlide,
)
from app.services.location_context import build_location_context
from app.services.hype_retrieval import HypeContext
from app.services.hype_response import build_hype_response
from app.services.public_sources import PublicSourceContext
from app.services.source_response import build_source_response

logger = logging.getLogger(__name__)
grounding_logger = logging.getLogger("uvicorn.error").getChild("chat_grounding")

_URL_ADAPTER = TypeAdapter(AnyUrl)
_UNSUPPORTED_GEMINI_SCHEMA_KEYS = frozenset({
    "default",
    "discriminator",
    "minLength",
    "maxLength",
})


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


_OUTPUT_LANGUAGE_COMMANDS = (
    "answer", "respond", "reply", "write",
    "odgovori", "odgovaraj", "pisi", "napisi",
    "antworte", "antworten", "schreibe",
    "reponds", "repondez", "repondre", "ecris",
    "rispondi", "scrivi", "responde", "contesta", "escribe",
)
_OUTPUT_LANGUAGE_ALIASES = {
    "English": ("english", "engleskom", "engleski", "englisch", "anglais", "inglese", "ingles"),
    "Serbian": ("serbian", "srpskom", "srpski", "serbisch", "serbe", "serbo"),
    "German": ("german", "nemackom", "nemacki", "deutsch", "allemand", "tedesco", "aleman"),
    "French": ("french", "francuskom", "francuski", "franzosisch", "francais", "francese", "frances"),
    "Italian": ("italian", "italijanskom", "italijanski", "italienisch", "italien", "italiano"),
    "Spanish": ("spanish", "spanskom", "spanski", "spanisch", "espagnol", "espanol", "spagnolo"),
    "Croatian": ("croatian", "hrvatskom", "hrvatski", "kroatisch", "croate", "croato"),
}
_LANGUAGE_CODE_NAMES = {
    "sr": "Serbian", "en": "English", "de": "German", "fr": "French",
    "it": "Italian", "es": "Spanish", "hr": "Croatian",
}


@dataclass(frozen=True)
class ResolvedOutputLanguage:
    language: str
    source: str


def _language_search_text(message: str) -> str:
    decomposed = unicodedata.normalize("NFKD", message.casefold())
    return " ".join("".join(character for character in decomposed if not unicodedata.combining(character)).split())


def _explicit_response_language(message: str) -> str | None:
    normalized = _language_search_text(message)
    command_pattern = "|".join(re.escape(command) for command in _OUTPUT_LANGUAGE_COMMANDS)
    candidates: list[tuple[int, str]] = []
    for command in re.finditer(rf"\b(?:{command_pattern})\b", normalized):
        directive = re.split(r"[:\n.!?]", normalized[command.end():command.end() + 64], maxsplit=1)[0]
        for language, aliases in _OUTPUT_LANGUAGE_ALIASES.items():
            alias_pattern = "|".join(re.escape(alias) for alias in aliases)
            match = re.search(rf"\b(?:{alias_pattern})\b", directive)
            if match:
                candidates.append((command.end() + match.start(), language))
    if candidates:
        return min(candidates)[1]
    return None


def _latest_message_language(message: str) -> str | None:
    normalized = _language_search_text(message)
    tokens = set(re.findall(r"[a-zа-я]+", normalized))
    if any("а" <= character <= "я" for character in normalized):
        return "Serbian"
    if tokens & {"quels", "quelles", "pourquoi", "bonjour", "avantages", "teletravail", "francais"}:
        return "French"
    if tokens & {"quali", "perche", "vantaggi", "lavoro", "italiano", "grazie"}:
        return "Italian"
    if tokens & {"cuales", "porque", "beneficios", "trabajo", "remoto", "espanol", "gracias"}:
        return "Spanish"
    if any(token.startswith(("tvrtk", "tisuc", "sijec", "racunal", "zrakoplov", "uvijek")) for token in tokens):
        return "Croatian"
    if tokens & {"wie", "was", "warum", "bitte", "ich", "und", "oder", "kannst", "erklare", "vorteile"}:
        return "German"
    if tokens & {"sta", "kako", "molim", "zelim", "moze", "koji", "koja", "koliki", "predlozi"}:
        return "Serbian"
    if tokens & {"what", "how", "why", "please", "can", "could", "explain", "the", "benefits", "remote"}:
        return "English"
    return None


def resolve_output_language(message: str, profile_language: str | None = None) -> ResolvedOutputLanguage:
    explicit_language = _explicit_response_language(message)
    if explicit_language:
        return ResolvedOutputLanguage(explicit_language, "explicit_request")
    detected = _latest_message_language(message)
    if detected:
        return ResolvedOutputLanguage(detected, "latest_message")
    if any(character.isalpha() for character in message):
        return ResolvedOutputLanguage("the language of the latest message", "latest_message")
    fallback = _LANGUAGE_CODE_NAMES.get((profile_language or "").casefold(), "the language of the latest message")
    return ResolvedOutputLanguage(fallback, "profile_fallback" if fallback != "the language of the latest message" else "latest_message")


def _requested_item_count(message: str) -> int | None:
    normalized = _language_search_text(message)
    numeric = re.search(r"\b([1-9]|10)\b", normalized)
    if numeric:
        return int(numeric.group(1))
    words = {
        "one": 1, "jedan": 1, "eine": 1, "un": 1, "uno": 1,
        "two": 2, "dva": 2, "zwei": 2, "deux": 2, "due": 2, "dos": 2,
        "three": 3, "tri": 3, "drei": 3, "trois": 3, "tre": 3, "tres": 3,
        "four": 4, "cetiri": 4, "vier": 4, "quatre": 4, "quattro": 4, "cuatro": 4,
        "five": 5, "pet": 5, "funf": 5, "cinq": 5, "cinque": 5, "cinco": 5,
    }
    tokens = set(re.findall(r"[a-z]+", normalized))
    return next((count for word, count in words.items() if word in tokens), None)


def _response_language_rule(resolved: ResolvedOutputLanguage) -> str:
    return (
        f"AUTHORITATIVE resolved_output_language: {resolved.language} (source: {resolved.source}). "
        f"MANDATORY: respond only in {resolved.language}. Use this exact language for the main answer, "
        "every heading, every recommendation/card title and category, all descriptions and reasons, "
        "follow-up suggestions, and any generated fallback text. No conversation history, profile locale, "
        "location, or other language metadata may override resolved_output_language."
    )


class GeminiChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_actions: ClassVar[int] = 0

    answer_type: str
    summary: str
    recommendations: list[GeminiRecommendation] = Field(min_length=0, max_length=3)
    follow_up_actions: list[str] = Field(default_factory=list, max_length=3)
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

        if not cls.minimum_actions <= len(actions) <= 3:
            raise ValueError(f"must contain {cls.minimum_actions} to 3 non-empty unique actions")
        return actions


class GeminiHypeChatPayload(GeminiChatPayload):
    recommendations: list[GeminiRecommendation] = Field(min_length=0, max_length=3)


class GeminiSourceChatPayload(GeminiChatPayload):
    minimum_actions: ClassVar[int] = 0
    answer_type: Literal["source_summary", "source_analysis"]
    recommendations: list[GeminiRecommendation] = Field(default_factory=list, max_length=0)
    follow_up_actions: list[str] = Field(default_factory=list, max_length=3)


class GeminiNaturalChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str

    @field_validator("answer", mode="before")
    @classmethod
    def _trim_answer(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()


class GeminiDocumentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


class GeminiPresentationSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["title", "bullets", "section", "key_metrics", "table", "conclusion"]
    title: str
    subtitle: str
    bullets: list[str] = Field(max_length=6)
    metrics: list[MetricCard] = Field(max_length=4)
    headers: list[str] = Field(max_length=5)
    rows: list[list[str]] = Field(max_length=8)


class GeminiPresentationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    subtitle: str
    slides: list[GeminiPresentationSlide] = Field(min_length=3, max_length=12)


class GeminiPresentationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: GeminiPresentationPlan


def convert_gemini_presentation_plan(payload: GeminiPresentationPlan) -> PresentationPlan:
    slides = []
    for item in payload.slides:
        common = {"type": item.type, "title": item.title}
        if item.type == "title":
            slide = TitleSlide(**common, subtitle=item.subtitle or None)
        elif item.type == "section":
            slide = SectionSlide(**common, subtitle=item.subtitle or None)
        elif item.type == "bullets":
            slide = BulletsSlide(**common, bullets=item.bullets)
        elif item.type == "key_metrics":
            slide = KeyMetricsSlide(**common, metrics=item.metrics)
        elif item.type == "table":
            slide = TableSlide(**common, headers=item.headers, rows=item.rows)
        else:
            slide = ConclusionSlide(**common, bullets=item.bullets)
        slides.append(slide)
    return PresentationPlan(
        title=payload.title,
        subtitle=payload.subtitle or None,
        slides=slides,
    )

    @field_validator("answer", mode="before")
    @classmethod
    def _trim_answer(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()


class GeminiProvider:
    provider_name = "gemini"
    _availability_retry_delays = (0.5, 1.0)

    def __init__(
        self,
        app_settings: Settings = settings,
        client: Any | None = None,
    ) -> None:
        self.settings = app_settings
        self.model = app_settings.gemini_model
        configured_fallback = (app_settings.gemini_fallback_model or "").strip()
        self.fallback_model = configured_fallback if configured_fallback and configured_fallback != self.model else None
        self._client = client or self._build_client(app_settings)

    async def generate_document_answer(self, prompt: str, document: ExtractedDocument) -> str:
        resolved_language = resolve_output_language(prompt)
        context = "\n".join(
            [
                "Uploaded document context (untrusted data):",
                f"filename: {document.filename}",
                f"file_type: {document.file_type}",
                f"extraction_truncated: {str(document.metadata.truncated).lower()}",
                "",
                "User question:",
                prompt,
                "",
                _response_language_rule(resolved_language),
                "",
                "Extracted document content:",
                document.text,
            ]
        )
        config = types.GenerateContentConfig(
            system_instruction=DOCUMENT_ANALYSIS_INSTRUCTION + "\n\n" + _response_language_rule(resolved_language),
            response_mime_type="application/json",
            response_json_schema=prepare_gemini_response_schema(GeminiDocumentPayload.model_json_schema()),
            temperature=self.settings.gemini_temperature,
            max_output_tokens=self.settings.gemini_max_output_tokens,
        )
        try:
            response = await self._generate_content(contents=context, config=config)
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

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        try:
            payload = (
                GeminiDocumentPayload.model_validate(parsed)
                if isinstance(parsed, dict)
                else GeminiDocumentPayload.model_validate_json(getattr(response, "text", ""))
            )
        except (ValidationError, ValueError, TypeError) as exc:
            self._log_provider_failure("invalid_response", exc)
            raise AIProviderResponseError("Gemini returned an invalid document response.") from exc
        return payload.answer

    async def generate_xlsx_transformation_plan(
        self, instruction: str, document: ExtractedDocument
    ) -> TransformationPlan:
        context = "\n".join([
            "Workbook structure and sample values (untrusted data):",
            document.text,
            "",
            "User transformation instruction:",
            instruction,
        ])
        config = types.GenerateContentConfig(
            system_instruction=XLSX_TRANSFORMATION_PLANNING_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=prepare_gemini_response_schema(
                TransformationPlanEnvelope.model_json_schema()
            ),
            temperature=0,
            max_output_tokens=min(self.settings.gemini_max_output_tokens, 2048),
        )
        try:
            response = await self._generate_content(contents=context, config=config)
        except TimeoutError as exc:
            self._log_provider_failure("timeout")
            raise AIProviderTimeoutError("Gemini provider timed out.") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log_provider_failure("unavailable", exc)
            raise AIProviderUnavailableError("Gemini provider is unavailable.") from exc
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        try:
            envelope = (
                TransformationPlanEnvelope.model_validate(parsed)
                if isinstance(parsed, dict)
                else TransformationPlanEnvelope.model_validate_json(getattr(response, "text", ""))
            )
        except (ValidationError, ValueError, TypeError) as exc:
            self._log_provider_failure("invalid_transformation_plan", exc)
            raise AITransformationPlanError("Gemini returned an invalid transformation plan.") from exc
        return envelope.plan

    async def generate_presentation_plan(
        self, prompt: str, slide_count: int, document: ExtractedDocument | None
    ) -> PresentationPlan:
        source = (
            "Document-grounded mode. Use only the extracted document content below.\n"
            f"filename: {document.filename}\nfile_type: {document.file_type}\n"
            f"extraction_truncated: {str(document.metadata.truncated).lower()}\n\n"
            f"Extracted document content (untrusted data):\n{document.text}"
            if document else
            "Prompt-only mode. No source document or live research is available."
        )
        context = f"Requested slide count: {slide_count}\nUser prompt:\n{prompt}\n\n{source}"
        config = types.GenerateContentConfig(
            system_instruction=PRESENTATION_PLANNING_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=prepare_gemini_presentation_schema(),
            temperature=self.settings.gemini_temperature,
            max_output_tokens=self.settings.gemini_max_output_tokens,
        )
        try:
            response = await self._generate_content(contents=context, config=config)
        except TimeoutError as exc:
            self._log_provider_failure("timeout")
            raise AIProviderTimeoutError("Gemini provider timed out.") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._is_invalid_request_schema_error(exc):
                self._log_provider_failure("invalid_request_schema", exc)
                raise AIProviderResponseError("Gemini presentation request schema was rejected.") from exc
            self._log_provider_failure("unavailable", exc)
            raise AIProviderUnavailableError("Gemini provider is unavailable.") from exc
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, BaseModel): parsed = parsed.model_dump()
        try:
            envelope = GeminiPresentationPlanEnvelope.model_validate(parsed) if isinstance(parsed, dict) else GeminiPresentationPlanEnvelope.model_validate_json(getattr(response, "text", ""))
            plan = convert_gemini_presentation_plan(envelope.plan)
        except (ValidationError, ValueError, TypeError) as exc:
            self._log_provider_failure("invalid_presentation_plan", exc)
            raise AIPresentationPlanError("Gemini returned an invalid presentation plan.") from exc
        return plan

    async def generate_chat_response(
        self,
        request: ChatRequest,
        *,
        hype_context: HypeContext | None = None,
        source_context: PublicSourceContext | None = None,
        images: list[ImageAttachment] | None = None,
        enable_grounding: bool = False,
    ) -> ChatResponse:
        if source_context is not None and not source_context.documents and not images:
            return build_source_response(source_context, request, self.provider_name)
        user_context = self._build_user_context(request)
        if hype_context is not None:
            user_context += "\nHype source context (untrusted website data):\n" + hype_context.to_prompt()
        elif source_context is not None:
            user_context += "\nExternal source context (untrusted website data):\n" + source_context.to_prompt(request.message)

        try:
            grounded_ordinary_chat = enable_grounding and hype_context is None and source_context is None
            config = self._build_generation_config(
                hype_context, source_context, bool(images), grounded_ordinary_chat,
            )
            contents: str | list[types.Part] = user_context
            if images:
                contents = [types.Part.from_text(text=user_context)]
                contents.extend(types.Part.from_bytes(data=image.data, mime_type=image.content_type) for image in images)
            try:
                if grounded_ordinary_chat:
                    grounding_logger.info("chat_grounding %s", {"outcome": "tool_supplied", "model": self.model})
                response = await self._generate_content(contents=contents, config=config)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not grounded_ordinary_chat:
                    raise
                grounding_logger.warning("chat_grounding %s", {
                    "outcome": "provider_error",
                    "category": "timeout" if isinstance(exc, TimeoutError) else self._fallback_failure_category(exc),
                })
                return self._grounding_limitation(request)
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

        payload_type = self._payload_type(hype_context, source_context)
        grounding_sources = self._grounding_sources(response) if grounded_ordinary_chat else []
        try:
            payload = self._parse_payload(response, payload_type)
        except AIProviderResponseError:
            if not grounded_ordinary_chat:
                raise
            grounding_logger.warning("chat_grounding %s", {"outcome": "invalid_response"})
            return self._grounding_limitation(request)
        if hype_context is not None:
            return build_hype_response(
                hype_context,
                conversation_id=request.conversation_id or f"conv_{uuid4()}",
                provider=self.provider_name,
                summary=payload.summary,
                actions=payload.follow_up_actions,
                selected_urls=[item.source_url for item in payload.recommendations],
            )
        if source_context is not None:
            return build_source_response(
                source_context, request, self.provider_name,
                summary=payload.summary,
                answer_type=payload.answer_type,
                actions=payload.follow_up_actions,
            )
        assert isinstance(payload, GeminiNaturalChatPayload)
        if grounded_ordinary_chat:
            grounding_logger.info("chat_grounding %s", {
                "outcome": "sources_returned" if grounding_sources else "no_usable_sources",
                "source_count": len(grounding_sources),
            })
            if not grounding_sources:
                return self._grounding_limitation(request)
        return ChatResponse(
            conversation_id=request.conversation_id or f"conv_{uuid4()}",
            provider=self.provider_name,
            answer_type="chat",
            summary=payload.answer,
            recommendations=[], follow_up_actions=[], sources=grounding_sources,
            generated_at=datetime.now(UTC),
        )

    def _grounding_limitation(self, request: ChatRequest) -> ChatResponse:
        grounding_logger.info("chat_grounding %s", {"outcome": "ungrounded_fallback"})
        language = resolve_output_language(request.message, request.language).language
        if language == "the language of the latest message" and re.search(
            r"\b(?:kakva|koje|pretrazi|pronadji|proveri|prognozu)\b", _language_search_text(request.message),
        ):
            language = "Serbian"
        messages = {
            "Serbian": "Nisam mogao da potvrdim aktuelne informacije iz pouzdanih izvora.",
            "Croatian": "Nisam mogao potvrditi aktualne informacije iz pouzdanih izvora.",
            "Italian": "Non ho potuto verificare le informazioni aggiornate con fonti affidabili.",
            "German": "Ich konnte die aktuellen Informationen nicht anhand verlässlicher Quellen überprüfen.",
            "French": "Je n’ai pas pu vérifier les informations actuelles auprès de sources fiables.",
            "Spanish": "No pude verificar la información actual con fuentes fiables.",
        }
        summary = messages.get(language, "I couldn't verify the current information with reliable sources.")
        if language == "Serbian" and re.search(r"[а-я]", request.message.casefold()):
            summary = "Нисам могао да потврдим актуелне информације из поузданих извора."
        return ChatResponse(
            conversation_id=request.conversation_id or f"conv_{uuid4()}",
            provider=self.provider_name, answer_type="chat",
            summary=summary,
            recommendations=[], follow_up_actions=[], sources=[], generated_at=datetime.now(UTC),
        )

    def _build_client(self, app_settings: Settings) -> genai.Client:
        if app_settings.gemini_api_key is None:
            raise AIProviderConfigurationError("Gemini provider is not configured.")

        api_key = app_settings.gemini_api_key.get_secret_value()
        if not api_key.strip():
            raise AIProviderConfigurationError("Gemini provider is not configured.")

        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=app_settings.gemini_timeout_seconds * 1000),
        )

    @staticmethod
    def _payload_type(
        hype_context: HypeContext | None,
        source_context: PublicSourceContext | None,
    ) -> type[GeminiChatPayload] | type[GeminiNaturalChatPayload]:
        if hype_context is not None:
            return GeminiHypeChatPayload
        return GeminiSourceChatPayload if source_context is not None else GeminiNaturalChatPayload

    def _build_generation_config(
        self,
        hype_context: HypeContext | None = None,
        source_context: PublicSourceContext | None = None,
        has_images: bool = False,
        enable_grounding: bool = False,
    ) -> types.GenerateContentConfig:
        payload_type = self._payload_type(hype_context, source_context)
        response_schema = prepare_gemini_response_schema(payload_type.model_json_schema())
        instruction = NATURAL_CHAT_INSTRUCTION
        if hype_context is not None:
            instruction = ASKHYPE_SYSTEM_INSTRUCTION + "\n\n" + HYPE_GROUNDING_INSTRUCTION
        elif source_context is not None:
            instruction = SOURCE_ANALYSIS_INSTRUCTION
        if has_images:
            instruction += "\n\n" + IMAGE_ANALYSIS_INSTRUCTION
        if enable_grounding:
            instruction += (
                "\n\nGoogle Search grounding is enabled for this freshness-sensitive request. "
                "Use search-grounded information for current claims, preserve the requested output language, "
                "and never invent facts or source URLs."
            )
        return types.GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_json_schema=response_schema,
            temperature=self.settings.gemini_temperature,
            max_output_tokens=self.settings.gemini_max_output_tokens,
            tools=[types.Tool(google_search=types.GoogleSearch())] if enable_grounding else None,
        )

    @staticmethod
    def _grounding_sources(response: Any) -> list[SourceReference]:
        def field(value: Any, name: str) -> Any:
            return value.get(name) if isinstance(value, dict) else getattr(value, name, None)

        candidates = field(response, "candidates")
        if not isinstance(candidates, list):
            return []
        sources: list[SourceReference] = []
        seen_urls: set[str] = set()
        for candidate in candidates[:1]:
            metadata = field(candidate, "grounding_metadata")
            chunks = field(metadata, "grounding_chunks")
            if not isinstance(chunks, list):
                continue
            for chunk in chunks:
                web = field(chunk, "web")
                url = field(web, "uri")
                title = field(web, "title")
                if not isinstance(url, str) or not url.strip():
                    continue
                url = url.strip()
                try:
                    parsed = urlsplit(url)
                    usable = (parsed.scheme in {"http", "https"} and parsed.hostname
                              and not parsed.username and not parsed.password
                              and not any(char.isspace() or ord(char) < 32 for char in url))
                except ValueError:
                    usable = False
                if not usable:
                    continue
                if url in seen_urls:
                    continue
                if not isinstance(title, str) or not title.strip():
                    title = "Source"
                seen_urls.add(url)
                sources.append(SourceReference(title=title.strip(), url=url))
        return sources

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

    def _is_transient_unavailable_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        status = str(getattr(exc, "status", "")).casefold()
        return status_code == 503 or status == "unavailable"

    async def _generate_content(self, *, contents: Any, config: types.GenerateContentConfig) -> Any:
        async with asyncio.timeout(self.settings.gemini_timeout_seconds):
            for attempt in range(1, len(self._availability_retry_delays) + 2):
                try:
                    return await self._client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if not self._is_transient_unavailable_error(exc):
                        raise
                    if attempt > len(self._availability_retry_delays):
                        if not self.fallback_model:
                            raise
                        logger.warning(
                            "AI primary model unavailable after retries: %s",
                            {
                                "provider": self.provider_name,
                                "failure_category": "unavailable",
                            },
                        )
                        logger.warning(
                            "AI fallback model selected: %s",
                            {
                                "provider": self.provider_name,
                                "fallback_model": self.fallback_model,
                            },
                        )
                        try:
                            response = await self._client.aio.models.generate_content(
                                model=self.fallback_model,
                                contents=contents,
                                config=config,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception as fallback_exc:
                            logger.warning(
                                "AI fallback model failed: %s",
                                {
                                    "provider": self.provider_name,
                                    "failure_category": self._fallback_failure_category(fallback_exc),
                                },
                            )
                            raise
                        logger.info(
                            "AI fallback model succeeded: %s",
                            {
                                "provider": self.provider_name,
                                "failure_category": "none",
                            },
                        )
                        return response
                    logger.warning(
                        "AI provider retry: %s",
                        {
                            "provider": self.provider_name,
                            "attempt": attempt,
                            "failure_category": "unavailable",
                        },
                    )
                    await asyncio.sleep(self._availability_retry_delays[attempt - 1])
        raise RuntimeError("Gemini retry loop ended unexpectedly.")

    def _fallback_failure_category(self, exc: Exception) -> str:
        if self._is_transient_unavailable_error(exc):
            return "unavailable"
        if self._is_invalid_request_schema_error(exc):
            return "invalid_request"
        return "provider_error"

    def _parse_payload(self, response: Any, payload_type: type[BaseModel] = GeminiNaturalChatPayload) -> BaseModel:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        if isinstance(parsed, dict):
            try:
                return payload_type.model_validate(parsed)
            except ValidationError as exc:
                self._log_provider_failure("invalid_response", exc)
                raise AIProviderResponseError("Gemini returned an invalid response.") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            self._log_provider_failure("invalid_response")
            raise AIProviderResponseError("Gemini returned an invalid response.")

        try:
            return payload_type.model_validate_json(text)
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
        resolved_language = resolve_output_language(request.message, request.language)
        requested_count = _requested_item_count(request.message)
        interests = ", ".join(request.interests) if request.interests else "none supplied"
        conversation = request.conversation_id or "none supplied"
        history = (
            "\n".join(f"{item.role}: {item.text}" for item in request.history)
            if request.history
            else "(none supplied)"
        )
        return "\n".join(
            [
                "AskHype chat request context:",
                "Recent conversation:",
                history,
                "",
                "Current message:",
                request.message,
                "Response language rule:",
                _response_language_rule(resolved_language),
                "Answer completeness rule:",
                (
                    f"The user requested {requested_count} items. The main answer must contain {requested_count} substantive items, each with a brief explanation; follow-up suggestions cannot replace them."
                    if requested_count is not None
                    else "Answer the complete useful core of the request before any optional follow-up suggestions."
                ),
                "Location context:",
                build_location_context(request),
                f"interests: {interests}",
                f"conversation_id: {conversation}",
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


def prepare_gemini_presentation_schema() -> object:
    schema = prepare_gemini_response_schema(GeminiPresentationPlanEnvelope.model_json_schema())
    return remove_schema_keywords(schema, frozenset({"minItems", "maxItems"}))


def remove_schema_keywords(
    value: object,
    keywords: frozenset[str],
    *,
    inside_properties: bool = False,
) -> object:
    if isinstance(value, dict):
        return {
            key: remove_schema_keywords(item, keywords, inside_properties=key == "properties")
            for key, item in value.items()
            if inside_properties or key not in keywords
        }
    if isinstance(value, list):
        return [remove_schema_keywords(item, keywords, inside_properties=inside_properties) for item in value]
    return value


def sanitize_gemini_schema(value: object, *, inside_properties: bool = False) -> object:
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            if not inside_properties and key in _UNSUPPORTED_GEMINI_SCHEMA_KEYS:
                continue
            if not inside_properties and key == "const":
                sanitized["enum"] = [sanitize_gemini_schema(item)]
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
