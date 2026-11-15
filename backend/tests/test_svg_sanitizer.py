import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.providers.generative_svg import GenerativeSvgProvider
from app.renderers.svg_preview import chrome_command
from app.renderers.svg_sanitizer import (
    MAX_ELEMENTS,
    MAX_SVG_BYTES,
    SvgValidationError,
    extract_svg_document,
    sanitize_svg,
)
from app.schemas.generative_svg import ArtDirection

SAFE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<defs>
  <linearGradient id="sky"><stop offset="0" style="stop-color:#ffcc00;stop-opacity:0.8"/><stop offset="1" stop-color="#7857c8" stop-opacity="1"/></linearGradient>
  <clipPath id="clip"><circle cx="100" cy="100" r="80"/></clipPath>
  <mask id="fade"><rect width="200" height="200" fill="#fff"/></mask>
  <filter id="glow"><feGaussianBlur stdDeviation="6"/></filter>
</defs>
<style>
@keyframes float { from { transform: translate(0,0); opacity: .8; } 50% { transform: translate(0,-20px); opacity: 1; } to { transform: translate(0,0); opacity: .8; } }
.character { animation: float 4s ease-in-out infinite; transform-origin: center; fill: #ffd45a; font-family: sans-serif; font-size: 24px; stroke-dasharray: 8 4; stroke-dashoffset: 2; }
</style>
<rect width="1280" height="720" fill="url(#sky)"/>
<g class="character" clip-path="url(#clip)" mask="url(#fade)"><circle cx="100" cy="100" r="70" fill="#ffd45a" filter="url(#glow)"/><text x="100" y="110" text-anchor="middle" font-size="24" font-family="sans-serif">Zdravo</text></g>
<g id="second-character" transform="translate(300 200)"><rect width="80" height="120" rx="20" fill="#4cc9f0"/></g>
</svg>'''


def test_safe_gradients_masks_keyframes_transforms_opacity_text_and_groups_pass():
    result = sanitize_svg(SAFE_SVG, duration_seconds=12)
    assert result.css_keyframes == 1
    assert result.element_count >= 10
    assert "linearGradient" in result.content and "second-character" in result.content


@pytest.mark.parametrize("response", [
    SAFE_SVG,
    f"```svg\n{SAFE_SVG}\n```",
    f"```xml\n{SAFE_SVG}\n```",
    f"```\n{SAFE_SVG}\n```",
    f"Here is the requested artifact:\n{SAFE_SVG}",
    f"{SAFE_SVG}\nGenerated as requested.",
    f"  \n{SAFE_SVG}\n  ",
])
def test_extract_svg_document_accepts_one_complete_document(response):
    extracted = extract_svg_document(response)
    assert extracted.startswith("<svg") and extracted.endswith("</svg>")
    assert sanitize_svg(extracted, duration_seconds=12).element_count >= 10


@pytest.mark.parametrize(("response", "code"), [
    ("There is no vector document.", "missing_svg"),
    ('<svg xmlns="http://www.w3.org/2000/svg"><g>', "incomplete_svg"),
    ('<svg xmlns="http://www.w3.org/2000/svg"/><svg xmlns="http://www.w3.org/2000/svg"></svg>', "ambiguous_svg"),
    ('<svg xmlns="http://www.w3.org/2000/svg"><svg></svg></svg>', "ambiguous_svg"),
])
def test_extract_svg_document_rejects_missing_incomplete_or_ambiguous_documents(response, code):
    with pytest.raises(SvgValidationError) as captured:
        extract_svg_document(response)
    assert captured.value.code == code


def test_extraction_does_not_bypass_sanitizer_security():
    response = 'Explanation\n<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>\nDone'
    with pytest.raises(SvgValidationError, match="disallowed_tag"):
        sanitize_svg(extract_svg_document(response), duration_seconds=10)


def test_forbidden_tokens_in_inert_css_comments_do_not_trigger_false_positive():
    source = '<svg xmlns="http://www.w3.org/2000/svg"><style>/* no @import or url() */ .x{opacity:1}</style><g class="x"/></svg>'
    assert sanitize_svg(source, duration_seconds=10).element_count == 3


def test_safe_gradient_stop_css_and_attributes_are_supported():
    source = '''<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g">
    <stop offset="0" style="stop-color:#ffcc00;stop-opacity:0.8"/>
    <stop offset="1" stop-color="rgb(10, 20, 30)" stop-opacity=".25"/>
    </linearGradient></defs><rect width="10" height="10" fill="url(#g)"/></svg>'''
    result = sanitize_svg(source, duration_seconds=10)
    assert "stop-color:#ffcc00" in result.content


@pytest.mark.parametrize("declaration", [
    "stop-color:url(http://example.com/color)",
    "stop-color:javascript:alert(1)",
    "stop-color:var(--gradient-color)",
    "stop-color:not-a-real-color",
    "stop-opacity:expression(1)",
    "stop-opacity:2",
    "stop-opacity:-1",
])
def test_unsafe_gradient_stop_css_values_are_rejected(declaration):
    source = f'<svg xmlns="http://www.w3.org/2000/svg"><style>.x{{{declaration}}}</style><stop class="x"/></svg>'
    with pytest.raises(SvgValidationError):
        sanitize_svg(source, duration_seconds=10)


@pytest.mark.parametrize(("name", "value"), [("stop-color", "var(--x)"), ("stop-opacity", "2")])
def test_unsafe_gradient_stop_attributes_are_rejected(name, value):
    source = f'<svg xmlns="http://www.w3.org/2000/svg"><stop {name}="{value}"/></svg>'
    with pytest.raises(SvgValidationError, match="invalid_attribute"):
        sanitize_svg(source, duration_seconds=10)


@pytest.mark.parametrize(("fragment", "code"), [
    ("<script>alert(1)</script>", "disallowed_tag"),
    ("<foreignObject><div>bad</div></foreignObject>", "disallowed_tag"),
    ('<circle onclick="alert(1)"/>', "event_handler"),
    ('<text href="javascript:alert(1)">x</text>', "disallowed_attribute"),
    ('<text href="https://example.com">x</text>', "disallowed_attribute"),
    ("<style>.x{fill:url(https://example.com/x)}</style>", "unsafe_css"),
    ("<style>.x{fill:url(#local)}</style>", "unsafe_css"),
    ("<style>@import 'https://example.com/x';</style>", "unsafe_css"),
    ('<text font-family="Remote Fancy Font">x</text>', "external_font"),
])
def test_unsafe_svg_features_are_rejected(fragment, code):
    source = f'<svg xmlns="http://www.w3.org/2000/svg">{fragment}</svg>'
    with pytest.raises(SvgValidationError) as captured:
        sanitize_svg(source, duration_seconds=10)
    assert captured.value.code == code


def test_oversized_excessive_and_malformed_svg_are_rejected():
    with pytest.raises(SvgValidationError, match="document_too_large"):
        sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><desc>' + "x" * MAX_SVG_BYTES + "</desc></svg>", duration_seconds=10)
    excessive = '<svg xmlns="http://www.w3.org/2000/svg">' + "<circle/>" * MAX_ELEMENTS + "</svg>"
    with pytest.raises(SvgValidationError, match="too_many_elements"):
        sanitize_svg(excessive, duration_seconds=10)
    with pytest.raises(SvgValidationError, match="invalid_xml"):
        sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><g></svg>', duration_seconds=10)


def test_invalid_xml_diagnostic_is_structural_and_does_not_leak_source_data():
    secret = "TOP_SECRET_PROMPT_VALUE"
    source = f'<svg xmlns="http://www.w3.org/2000/svg"><g><text>{secret}</text></svg>'
    with pytest.raises(SvgValidationError) as captured:
        sanitize_svg(source, duration_seconds=10)
    error = captured.value
    assert error.code == "invalid_xml"
    assert "line 1 column" in error.detail
    assert "mismatched tag" in error.detail
    assert secret not in error.detail
    assert "<svg" not in error.detail


def test_animation_and_filter_limits_are_enforced():
    with pytest.raises(SvgValidationError, match="animation_too_long"):
        sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><style>.x{animation: spin 16s linear}</style></svg>', duration_seconds=10)
    with pytest.raises(SvgValidationError, match="unsafe_filter"):
        sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><filter id="x"><feGaussianBlur stdDeviation="30"/></filter></svg>', duration_seconds=10)


def test_safe_composite_filter_primitives_are_supported():
    source = '''<svg xmlns="http://www.w3.org/2000/svg"><filter id="x">
    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur"/>
    <feComposite in="SourceGraphic" in2="blur" operator="over" result="combined"/>
    <feComposite in="SourceGraphic" in2="blur" operator="arithmetic" k1="0" k2="1" k3="1" k4="0"/>
    </filter></svg>'''
    result = sanitize_svg(source, duration_seconds=10)
    assert "feComposite" in result.content


@pytest.mark.parametrize(("attribute", "value"), [
    ("operator", "multiply"),
    ("k1", "expression(1)"),
    ("k2", "url(http://example.com/value)"),
    ("k3", "NaN"),
    ("k4", "Infinity"),
    ("k1", "10.01"),
    ("k2", "-10.01"),
])
def test_unsafe_composite_filter_values_are_rejected(attribute, value):
    source = f'<svg xmlns="http://www.w3.org/2000/svg"><filter><feComposite {attribute}="{value}"/></filter></svg>'
    with pytest.raises(SvgValidationError):
        sanitize_svg(source, duration_seconds=10)


def test_composite_filter_rejects_event_handlers_and_external_references():
    with pytest.raises(SvgValidationError, match="event_handler"):
        sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><filter><feComposite onclick="bad()"/></filter></svg>', duration_seconds=10)
    with pytest.raises(SvgValidationError, match="external_reference"):
        sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><filter><feComposite in2="https://example.com/filter"/></filter></svg>', duration_seconds=10)


def test_chrome_command_disables_javascript_and_network(tmp_path):
    command = chrome_command(tmp_path / "safe.svg", tmp_path / "safe.png", tmp_path / "profile", virtual_time_ms=5000)
    assert "--disable-javascript" in command
    assert "--disable-background-networking" in command
    assert "--host-resolver-rules=MAP * ~NOTFOUND" in command
    assert command[-1].startswith("file:")
    assert all("shell" not in item for item in command)


def _direction() -> dict:
    return {"art_direction": {
        "title": "Različita scena", "duration_seconds": 10,
        "scene_description": "Jedna bogata vektorska scena.",
        "characters": [], "objects": [], "background_description": "Slojevita pozadina",
        "composition": "Asimetrična kompozicija", "visual_style": "Retro strip sa grubim linijama",
        "shape_language": "Ugaone forme", "palette": ["crvena", "plava"], "lighting": "Jako bočno svetlo",
        "line_treatment": "Debele teksturisane linije", "depth_style": "Tri ravni",
        "mood": "Energično", "motion_style": "Brzi ritmični pokreti",
        "timeline_beats": [{"start": 0, "duration": 10, "description": "Cela scena", "motion": "Ritmično"}],
    }}


def test_provider_repairs_artifact_once_with_safe_feedback_only():
    async def run():
        responses = [
            SimpleNamespace(parsed=_direction(), text=""),
            SimpleNamespace(parsed=None, text='<svg xmlns="http://www.w3.org/2000/svg"><script>private raw payload</script></svg>'),
            SimpleNamespace(parsed=None, text=SAFE_SVG),
        ]
        calls = []
        provider = GenerativeSvgProvider(client=SimpleNamespace())
        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return responses.pop(0)
        provider._gemini._generate_content = response
        artifact = await provider.generate("Napravi scenu")
        assert artifact.artifact_attempts == 2 and artifact.svg.css_keyframes == 1
        assert "code=disallowed_tag" in calls[-1]
        assert "private raw payload" not in calls[-1]
        assert len(calls) == 3
    asyncio.run(run())


def test_provider_repairs_malformed_xml_once_with_safe_parse_feedback():
    async def run():
        malformed = '<svg xmlns="http://www.w3.org/2000/svg"><g><text>PRIVATE</text></svg>'
        responses = [
            SimpleNamespace(parsed=_direction(), text=""),
            SimpleNamespace(parsed=None, text=malformed),
            SimpleNamespace(parsed=None, text=SAFE_SVG),
        ]
        calls = []
        provider = GenerativeSvgProvider(client=SimpleNamespace())

        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return responses.pop(0)

        provider._gemini._generate_content = response
        artifact = await provider.generate("PROMPT_SECRET")
        assert artifact.artifact_attempts == 2
        assert len(calls) == 3
        repair = calls[-1]
        assert "not well-formed XML" in repair
        assert "line 1 column" in repair
        assert "mismatched tag" in repair
        assert "PRIVATE" not in repair
        assert malformed not in repair

    asyncio.run(run())


def test_provider_stops_after_malformed_repair_without_third_attempt():
    async def run():
        malformed = '<svg xmlns="http://www.w3.org/2000/svg"><g></svg>'
        responses = [
            SimpleNamespace(parsed=_direction(), text=""),
            SimpleNamespace(parsed=None, text=malformed),
            SimpleNamespace(parsed=None, text=malformed),
        ]
        calls = []
        provider = GenerativeSvgProvider(client=SimpleNamespace())

        async def response(**kwargs):
            calls.append(kwargs["contents"])
            return responses.pop(0)

        provider._gemini._generate_content = response
        with pytest.raises(SvgValidationError) as captured:
            await provider.generate("Napravi scenu")
        assert captured.value.code == "artifact_invalid_after_repair"
        assert "invalid_xml" in captured.value.detail
        assert len(calls) == 3

    asyncio.run(run())


def test_art_direction_descriptive_fields_are_bounded():
    direction = ArtDirection.model_validate(_direction()["art_direction"])
    assert direction.visual_style.startswith("Retro")
