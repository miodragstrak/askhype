import asyncio
from typing import Any, Protocol

from google.genai import types
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, settings
from app.providers.exceptions import (
    AIAnimationPlanError,
    AIProviderConfigurationError,
    AIProviderRateLimitError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.providers.gemini import GeminiProvider, prepare_gemini_response_schema, remove_schema_keywords
from app.schemas.animations import (
    AnimationAppearance,
    AnimationBackground,
    AnimationCharacter,
    AnimationObject,
    AnimationPlan,
    AnimationPlanEnvelope,
    TimelineEvent,
    TimelineParameters,
)

ANIMATION_PLANNING_INSTRUCTION = """Create one short, safe 2D cartoon animation plan.
Return only the requested structured plan. Never return code, HTML, SVG, CSS, scripts, URLs, or executable content.
Use only the controlled character, object, background, expression, color, and action values allowed by the schema.
Keep the scene visually clear, use no more than three characters, and place events inside the total duration.
Use Serbian text when the requested language is sr. Speech and thought text must be concise."""


class AnimationProvider(Protocol):
    provider_name: str
    model: str

    async def generate_plan(self, prompt: str, language: str) -> AnimationPlan: ...


def prepare_gemini_animation_schema() -> object:
    schema = prepare_gemini_response_schema(AnimationPlanEnvelope.model_json_schema())
    # Application-side Pydantic validation remains authoritative; keep the provider
    # schema within Gemini's conservative structured-output subset.
    return remove_schema_keywords(
        schema, frozenset({"minItems", "maxItems", "pattern", "exclusiveMinimum"}),
    )


class GeminiAnimationProvider:
    provider_name = "gemini"

    def __init__(self, app_settings: Settings = settings, client: Any | None = None) -> None:
        model = (app_settings.gemini_animation_model or "").strip() or app_settings.gemini_model
        if not model:
            raise AIProviderConfigurationError("Gemini animation model is not configured.")
        provider_settings = app_settings.model_copy(update={"gemini_model": model})
        self.model = model
        self._gemini = GeminiProvider(provider_settings, client=client)
        self.settings = provider_settings

    async def generate_plan(self, prompt: str, language: str) -> AnimationPlan:
        config = types.GenerateContentConfig(
            system_instruction=ANIMATION_PLANNING_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=prepare_gemini_animation_schema(),
            temperature=min(self.settings.gemini_temperature, 0.5),
            max_output_tokens=self.settings.gemini_max_output_tokens,
        )
        contents = f"Requested language: {language}\nAnimation request:\n{prompt}"
        try:
            response = await self._gemini._generate_content(contents=contents, config=config)
        except TimeoutError as exc:
            raise AIProviderTimeoutError("Animation provider timed out.") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            status = str(getattr(exc, "status", "")).casefold()
            if code == 429 or status == "resource_exhausted":
                raise AIProviderRateLimitError("Animation provider is rate limited.") from exc
            if code == 400 or status == "invalid_argument":
                raise AIProviderResponseError("Animation request schema was rejected.") from exc
            raise AIProviderUnavailableError("Animation provider is unavailable.") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        try:
            envelope = (
                AnimationPlanEnvelope.model_validate(parsed)
                if isinstance(parsed, dict)
                else AnimationPlanEnvelope.model_validate_json(getattr(response, "text", ""))
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise AIAnimationPlanError("Gemini returned an invalid animation plan.") from exc
        return envelope.plan


class MockAnimationProvider:
    provider_name = "mock"
    model = "mock-animation-v1"

    async def generate_plan(self, prompt: str, language: str) -> AnimationPlan:
        return AnimationPlan(
            title="Dečak i robot u parku" if language == "sr" else "A child and robot in the park",
            duration_seconds=12,
            background=AnimationBackground(type="park", description="Sunčan park sa drvećem", palette="day"),
            characters=[
                AnimationCharacter(
                    id="child", type="child", name="Dečak", x=36, y=78, scale=0.9,
                    appearance=AnimationAppearance(body_color="blue", accent_color="yellow", hair_style="short"),
                    expression="happy",
                ),
                AnimationCharacter(
                    id="robot", type="robot", name="Robot", x=62, y=76, scale=1,
                    appearance=AnimationAppearance(body_color="gray", accent_color="blue", accessory="antenna"),
                    expression="neutral",
                ),
            ],
            objects=[AnimationObject(id="rocket", type="rocket", x=78, y=20, scale=0.8, color="red")],
            timeline=[
                TimelineEvent(start=1, duration=2, target_id="robot", action="wave"),
                TimelineEvent(start=3, duration=2, target_id="child", action="smile"),
                TimelineEvent(start=6, duration=2, target_id="child", action="look_up"),
                TimelineEvent(start=6, duration=2, target_id="robot", action="look_up"),
                TimelineEvent(start=7, duration=3, target_id="rocket", action="appear", parameters=TimelineParameters()),
            ],
        )
