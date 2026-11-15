import asyncio
import logging
from types import SimpleNamespace

import pytest
from google.genai import types

from app.core.config import Settings
from app.providers.generative_svg import SVG_ARTIFACT_MAX_OUTPUT_TOKENS, GenerativeSvgProvider
from app.renderers.svg_quality import validate_svg_quality
from app.renderers.svg_sanitizer import SvgValidationError, sanitize_svg


def _svg(body: str, style: str = "") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><style>{style}</style>{body}</svg>'


def _quality(body: str, style: str = ""):
    return validate_svg_quality(sanitize_svg(_svg(body, style), duration_seconds=10))


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


class _Models:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _ProviderError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__("provider failure")


def _provider_with_fallback(models: _Models) -> GenerativeSvgProvider:
    app_settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        gemini_model="primary-model",
        gemini_fallback_model="fallback-model",
        gemini_timeout_seconds=1,
    )
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GenerativeSvgProvider(app_settings, client=client)


def test_primary_success_does_not_call_fallback():
    async def run():
        models = _Models([SimpleNamespace(text="fallback")])
        provider = _provider_with_fallback(models)
        provider._gemini._generate_content = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(text="primary"))
        response = await provider._request_with_timing("art_direction", contents="safe", config=types.GenerateContentConfig())
        assert response.text == "primary"
        assert models.calls == []
    asyncio.run(run())


@pytest.mark.parametrize("failure", [TimeoutError(), _ProviderError(503)])
def test_primary_timeout_or_transient_failure_uses_fallback_once(failure):
    async def run():
        models = _Models([SimpleNamespace(text="fallback")])
        provider = _provider_with_fallback(models)
        async def primary(**kwargs): raise failure
        provider._gemini._generate_content = primary
        response = await provider._request_with_timing("artifact_initial", contents="safe", config=types.GenerateContentConfig())
        assert response.text == "fallback"
        assert len(models.calls) == 1
        assert models.calls[0]["model"] == "fallback-model"
    asyncio.run(run())


def test_primary_4xx_does_not_use_fallback():
    async def run():
        models = _Models([SimpleNamespace(text="unused")])
        provider = _provider_with_fallback(models)
        async def primary(**kwargs): raise _ProviderError(400)
        provider._gemini._generate_content = primary
        with pytest.raises(_ProviderError):
            await provider._request_with_timing("artifact_initial", contents="safe", config=types.GenerateContentConfig())
        assert models.calls == []
    asyncio.run(run())


@pytest.mark.parametrize("fallback_failure", [TimeoutError(), _ProviderError(503)])
def test_failed_fallback_is_attempted_only_once(fallback_failure):
    async def run():
        models = _Models([fallback_failure])
        provider = _provider_with_fallback(models)
        async def primary(**kwargs): raise TimeoutError()
        provider._gemini._generate_content = primary
        with pytest.raises(type(fallback_failure)):
            await provider._request_with_timing("artifact_initial", contents="safe", config=types.GenerateContentConfig())
        assert len(models.calls) == 1
    asyncio.run(run())


def test_generation_tracks_fallback_stage_without_exposing_model_in_response():
    async def run():
        models = _Models([SimpleNamespace(parsed=_direction(), text="")])
        provider = _provider_with_fallback(models)
        primary_outcomes = [TimeoutError(), SimpleNamespace(text=_svg(_character()))]

        async def primary(**kwargs):
            outcome = primary_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        provider._gemini._generate_content = primary
        artifact = await provider.generate("Napravi scenu")
        assert artifact.fallback_used is True
        assert artifact.fallback_stages == ("art_direction",)
        assert artifact.model == "primary-model"
        assert len(models.calls) == 1
    asyncio.run(run())


def test_animation_model_overrides_primary_but_not_configured_fallback():
    app_settings = Settings(
        _env_file=None,
        gemini_api_key="test-key",
        gemini_model="chat-model",
        gemini_animation_model="animation-model",
        gemini_fallback_model="fallback-model",
    )
    provider = GenerativeSvgProvider(app_settings, client=SimpleNamespace())
    assert provider.model == "animation-model"
    assert provider.fallback_model == "fallback-model"


def _character(x: int = 200, y: int = 150, extra: str = "") -> str:
    return (
        f'<g id="girl-character-root"><rect x="{x}" y="{y}" width="100" height="220"/>'
        f'<g class="head">{extra}<circle cx="{x + 50}" cy="{y + 35}" r="30"/></g>'
        f'<g class="arm"><line x1="{x + 10}" y1="{y + 100}" x2="{x - 10}" y2="{y + 170}"/></g></g>'
    )


def test_valid_grouped_character_with_small_local_motion_passes():
    style = """
    @keyframes headMove { 0% { transform: translate(0,0) rotate(0deg); } 100% { transform: translate(8px,2px) rotate(20deg); } }
    @keyframes armMove { 0% { transform: translate(0,0); } 100% { transform: translate(15px,0); } }
    .head { animation: headMove 4s infinite; } .arm { animation: armMove 4s infinite; }
    """
    result = _quality(_character(), style)
    assert result.passed


def test_decorative_background_may_extend_outside_safe_bounds():
    result = _quality('<g id="background"><rect x="-200" y="-100" width="1600" height="900"/></g>' + _character())
    assert result.passed


def test_simplified_character_without_anatomical_subgroups_passes():
    result = _quality('<g id="creature-root"><ellipse cx="400" cy="300" rx="80" ry="100"/><circle cx="375" cy="280" r="8"/><circle cx="425" cy="280" r="8"/></g>')
    assert result.passed


@pytest.mark.parametrize("x,y", [(-200, 150), (10, 150), (200, 5), (1180, 150)])
def test_character_outside_or_clipped_by_safe_margin_fails(x, y):
    result = _quality(_character(x, y))
    assert "primary_subject_outside_safe_bounds" in _codes(result)


def test_character_root_animation_cannot_move_subject_outside_safe_bounds():
    style = "@keyframes enter { from { transform: translate(0,0); } to { transform: translate(-300px,0); } } .character-motion { animation: enter 4s; }"
    body = _character().replace('id="girl-character-root"', 'id="girl-character-root" class="character-motion"')
    assert "primary_subject_outside_safe_bounds" in _codes(_quality(body, style))


@pytest.mark.parametrize(
    ("class_name", "transform", "code"),
    [
        ("head", "translate(30px,0)", "excessive_head_translation"),
        ("arm", "translate(30px,0)", "excessive_limb_translation"),
        ("head", "rotate(50deg)", "excessive_local_rotation"),
        ("arm", "scale(1.3)", "excessive_local_scale"),
        ("head", "scaleY(0.7)", "excessive_local_scale"),
    ],
)
def test_excessive_local_animation_fails(class_name, transform, code):
    style = f"@keyframes move {{ 0% {{ transform: none; }} 100% {{ transform: {transform}; }} }} .{class_name} {{ animation: move 2s infinite; }}"
    assert code in _codes(_quality(_character(), style))


def test_obvious_top_level_anatomical_group_fails():
    body = _character() + '<g id="detached-head"><circle cx="500" cy="200" r="30"/></g>'
    assert "detached_anatomical_group" in _codes(_quality(body))


def _direction() -> dict:
    return {"art_direction": {
        "title": "Scena", "duration_seconds": 10, "scene_description": "Scena",
        "characters": [], "objects": [], "background_description": "Pozadina",
        "composition": "Centar", "visual_style": "Vektor", "shape_language": "Meko",
        "palette": ["plava", "žuta"], "lighting": "Blago", "line_treatment": "Čisto",
        "depth_style": "Slojevito", "mood": "Mirno", "motion_style": "Suptilno",
        "timeline_beats": [{"start": 0, "duration": 10, "description": "Scena", "motion": "Blago"}],
    }}


def test_quality_failure_triggers_one_safe_repair_and_returns_repaired_artifact():
    async def run():
        rejected = _svg(_character(10, 100) + '<text x="10" y="20">PRIVATE_ARTIFACT</text>')
        repaired = _svg(_character())
        responses = [SimpleNamespace(parsed=_direction(), text=""), SimpleNamespace(text=rejected), SimpleNamespace(text=repaired)]
        calls = []
        provider = GenerativeSvgProvider(client=SimpleNamespace())

        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return responses.pop(0)

        provider._gemini._generate_content = response
        artifact = await provider.generate("SECRET_PROMPT")
        assert artifact.artifact_attempts == 2
        assert artifact.quality_gate_failures == 1
        assert artifact.quality_repair_attempted is True
        assert "outside safe viewport bounds" in calls[-1]
        assert rejected not in calls[-1]
        assert "PRIVATE_ARTIFACT" not in calls[-1]
        assert len(calls) == 3

    asyncio.run(run())


def test_provider_stage_timings_do_not_log_prompt_or_svg(caplog):
    async def run():
        secret_prompt = "PRIVATE_PROMPT_VALUE"
        artifact_svg = _svg(_character())
        responses = [SimpleNamespace(parsed=_direction(), text=""), SimpleNamespace(text=artifact_svg)]
        provider = GenerativeSvgProvider(client=SimpleNamespace())

        async def response(**kwargs):
            return responses.pop(0)

        provider._gemini._generate_content = response
        with caplog.at_level(logging.INFO, logger="app.providers.generative_svg"):
            await provider.generate(secret_prompt)
        messages = " ".join(record.getMessage() for record in caplog.records)
        assert "generative_svg_provider_request_started" in messages
        assert "generative_svg_provider_response_received" in messages
        assert "generative_svg_stage_completed" in messages
        assert secret_prompt not in messages
        assert artifact_svg not in messages

    asyncio.run(run())


def test_artifact_generation_uses_compact_token_budget_only():
    async def run():
        responses = [SimpleNamespace(parsed=_direction(), text=""), SimpleNamespace(text=_svg(_character()))]
        calls = []
        provider = GenerativeSvgProvider(client=SimpleNamespace())

        async def response(**kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        provider._gemini._generate_content = response
        await provider.generate("Napravi scenu")
        assert calls[0]["config"].max_output_tokens == provider.settings.gemini_max_output_tokens
        assert calls[1]["config"].max_output_tokens == SVG_ARTIFACT_MAX_OUTPUT_TOKENS

    asyncio.run(run())


def test_failed_quality_repair_stops_and_returns_safe_category():
    async def run():
        rejected = _svg(_character(10, 100))
        responses = [SimpleNamespace(parsed=_direction(), text=""), SimpleNamespace(text=rejected), SimpleNamespace(text=rejected)]
        provider = GenerativeSvgProvider(client=SimpleNamespace())
        calls = []

        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return responses.pop(0)

        provider._gemini._generate_content = response
        with pytest.raises(SvgValidationError) as captured:
            await provider.generate("Napravi scenu")
        assert captured.value.code == "artifact_quality_failed"
        assert "<svg" not in captured.value.detail
        assert len(calls) == 3

    asyncio.run(run())
