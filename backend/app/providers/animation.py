import asyncio
import copy
import json
import logging
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
Allowed character types: person, child, robot, animal, creature.
Allowed actions: enter_left, enter_right, exit_left, exit_right, move, wave, bounce, nod, shake, look_left, look_right, look_up, smile, surprised, speech, thought, appear, disappear.
Map woman/man/adult (žena/muškarac/odrasla osoba) to person; boy/girl/kid/child (dečak/devojčica/dete) to child; dog/cat and other ordinary animals (pas/mačka) to animal.
Map jump/hop/poskočiti to bounce. Use speech or thought for text bubbles, but omit the event when no actual bubble text is supplied by the user.
Never invent action names or character types. Timeline target_id values must reference IDs declared in characters or objects.
Use only the controlled character, object, background, expression, color, and action values allowed by the schema. Create exactly one scene.
Keep the scene visually clear, use no more than three characters, and place events inside the total duration.
Use Serbian text when the requested language is sr. Speech and thought text must be concise."""

logger = logging.getLogger(__name__)

CHARACTER_TYPE_ALIASES = {
    "woman": "person", "man": "person", "adult": "person",
    "boy": "child", "girl": "child", "kid": "child",
    "dog": "animal", "cat": "animal",
}
ACTION_ALIASES = {
    "jump": "bounce", "hop": "bounce", "wave_hand": "wave", "look_upward": "look_up",
}


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
        response = await self._request(contents, config)
        try:
            return _validate_animation_response(response)
        except ValidationError as exc:
            _log_validation_failure(exc, self.provider_name, self.model, attempt=1)
            if not _repairable_validation(exc):
                raise AIAnimationPlanError("Gemini returned an invalid animation plan.") from exc
            repair_contents = _repair_contents(contents, exc)
            repaired = await self._request(repair_contents, config)
            try:
                return _validate_animation_response(repaired)
            except ValidationError as repair_exc:
                _log_validation_failure(repair_exc, self.provider_name, self.model, attempt=2)
                raise AIAnimationPlanError("Gemini returned an invalid animation plan after repair.") from repair_exc
            except (ValueError, TypeError) as repair_exc:
                _log_response_shape_failure(self.provider_name, self.model, attempt=2)
                raise AIAnimationPlanError("Gemini returned malformed animation data after repair.") from repair_exc
        except (ValueError, TypeError) as exc:
            _log_response_shape_failure(self.provider_name, self.model, attempt=1)
            raise AIAnimationPlanError("Gemini returned malformed animation data.") from exc

    async def _request(self, contents: str, config: types.GenerateContentConfig) -> Any:
        try:
            return await self._gemini._generate_content(contents=contents, config=config)
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


def normalize_animation_payload(value: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    plan = normalized.get("plan")
    if not isinstance(plan, dict):
        return normalized
    characters = plan.get("characters")
    if isinstance(characters, list):
        for character in characters:
            if not isinstance(character, dict) or not isinstance(character.get("type"), str):
                continue
            character_type = character["type"].strip().casefold()
            character["type"] = CHARACTER_TYPE_ALIASES.get(character_type, character["type"])
    timeline = plan.get("timeline")
    if isinstance(timeline, list):
        kept: list[Any] = []
        for event in timeline:
            if not isinstance(event, dict):
                kept.append(event)
                continue
            action = event.get("action")
            if isinstance(action, str):
                action_key = action.strip().casefold()
                event["action"] = ACTION_ALIASES.get(action_key, action)
            if event.get("action") in {"speech", "thought"}:
                parameters = event.get("parameters")
                text = parameters.get("text") if isinstance(parameters, dict) else None
                if not isinstance(text, str) or not text.strip():
                    continue
            kept.append(event)
        plan["timeline"] = kept
    return normalized


def _validate_animation_response(response: Any) -> AnimationPlan:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, BaseModel):
        parsed = parsed.model_dump()
    if parsed is None:
        parsed = json.loads(getattr(response, "text", ""))
    if not isinstance(parsed, dict):
        raise TypeError("Animation response must be an object.")
    return AnimationPlanEnvelope.model_validate(normalize_animation_payload(parsed)).plan


def _repairable_validation(exc: ValidationError) -> bool:
    return bool(exc.errors()) and all(error.get("type") != "json_invalid" for error in exc.errors())


def _repair_contents(contents: str, exc: ValidationError) -> str:
    feedback = [
        {"path": ".".join(str(part) for part in error["loc"]), "category": error["type"]}
        for error in exc.errors()[:12]
    ]
    return (
        f"{contents}\n\nThe previous plan failed strict validation. Repair it once and return a complete replacement plan.\n"
        f"Validation feedback: {json.dumps(feedback, separators=(',', ':'))}\n"
        "Use only the allowed schema enums, declared target IDs, one scene, and grounded bubble text. Do not add code or new action/type values."
    )


def _value_shape(value: Any) -> str:
    if isinstance(value, str): return f"string(length={len(value)})"
    if isinstance(value, list): return f"array(length={len(value)})"
    if isinstance(value, dict): return f"object(fields={len(value)})"
    return type(value).__name__


def _log_validation_failure(exc: ValidationError, provider: str, model: str, *, attempt: int) -> None:
    errors = [{
        "category": error["type"],
        "path": ".".join(str(part) for part in error["loc"]),
        "value_shape": _value_shape(error.get("input")),
    } for error in exc.errors()[:12]]
    logger.warning("Animation plan validation failed: %s", {
        "provider": provider, "model": model, "attempt": attempt, "errors": errors,
    })


def _log_response_shape_failure(provider: str, model: str, *, attempt: int) -> None:
    logger.warning("Animation response shape invalid: %s", {
        "provider": provider, "model": model, "attempt": attempt, "category": "malformed_response",
    })


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
