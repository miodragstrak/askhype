import asyncio
import io
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from app.providers.generative_svg import GenerativeSvgProvider, merge_reference_art_direction
from app.renderers.reference_image import (
    MAX_REFERENCE_BYTES,
    MAX_REFERENCE_DIMENSION,
    ReferenceImageError,
    prepare_reference_image,
)
from app.schemas.generative_svg import ArtDirection, ReferenceArtAnalysis


def _image_bytes(image_format: str, size: tuple[int, int] = (64, 48)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#284b73").save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_supported_reference_images_are_decoded_by_content(image_format):
    prepared = prepare_reference_image(_image_bytes(image_format))
    assert prepared.width == 64 and prepared.height == 48
    assert prepared.mime_type in {"image/png", "image/jpeg"}
    assert prepared.data


def test_reference_image_rejects_unsupported_oversized_and_malformed_data():
    with pytest.raises(ReferenceImageError, match="unsupported_reference_image_type"):
        prepare_reference_image(_image_bytes("GIF"))
    with pytest.raises(ReferenceImageError, match="reference_image_too_large"):
        prepare_reference_image(b"x" * (MAX_REFERENCE_BYTES + 1))
    with pytest.raises(ReferenceImageError, match="malformed_reference_image"):
        prepare_reference_image(b"not an image")


def test_large_reference_is_downscaled_in_memory_without_creating_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prepared = prepare_reference_image(_image_bytes("PNG", (MAX_REFERENCE_DIMENSION + 200, 32)))
    assert prepared.was_downscaled is True
    assert max(prepared.width, prepared.height) == MAX_REFERENCE_DIMENSION
    assert list(tmp_path.iterdir()) == []


def _analysis() -> ReferenceArtAnalysis:
    return ReferenceArtAnalysis.model_validate({
        "dominant_palette": ["#101a3a", "#6655aa", "#ffd166"],
        "secondary_palette": ["#f4a6c1"],
        "contrast_level": "Mek, srednji kontrast",
        "lighting_style": "Difuzno mesečevo svetlo sa toplim sjajem",
        "shape_language": "Meke, zaobljene i slojevite forme",
        "line_treatment": "Tanke tamnoplave konture",
        "texture_feel": "Glatka slikovnica sa blagim zrnom",
        "depth_style": "Tri slojevite ravni sa atmosferskom dubinom",
        "composition_tendency": "Mirna centralna kompozicija",
        "mood": "Nežno, sanjivo i spokojno",
        "softness": "Visoka mekoća",
        "visual_complexity": "Umerena ilustrativna složenost",
        "background_character": "Duboka noćna atmosfera",
        "character_style_notes": "Jednostavni zaobljeni likovi slikovnice",
        "motion_style_suggestion": "Sporo lebdenje i blago pulsiranje",
        "confidence_notes": "Visoko poverenje u paletu i mekoću",
    })


def _direction() -> ArtDirection:
    return ArtDirection.model_validate({
        "title": "Robot kuva čaj",
        "duration_seconds": 12,
        "scene_description": "Robot kuva čaj u maloj kuhinji.",
        "characters": [{"name": "Robot", "role": "Kuvar", "appearance": "Mali metalni robot"}],
        "objects": [{"name": "Čajnik", "description": "Čajnik na šporetu"}],
        "background_description": "Mala funkcionalna kuhinja",
        "composition": "Robot i čajnik u centru kuhinje",
        "visual_style": "Čist tehnološki crtež",
        "shape_language": "Geometrijski oblici",
        "palette": ["#ffffff", "#222222"],
        "lighting": "Jasno dnevno svetlo",
        "line_treatment": "Oštre linije",
        "depth_style": "Dve ravni",
        "mood": "Vedro",
        "motion_style": "Precizni mehanički pokreti",
        "timeline_beats": [{"start": 0, "duration": 12, "description": "Robot kuva čaj", "motion": "Robot pomera čajnik"}],
    })


def test_reference_analysis_is_strict_and_bounded():
    assert _analysis().dominant_palette[0] == "#101a3a"
    with pytest.raises(ValidationError):
        ReferenceArtAnalysis.model_validate({**_analysis().model_dump(), "unknown": "bad"})
    with pytest.raises(ValidationError):
        ReferenceArtAnalysis.model_validate({**_analysis().model_dump(), "mood": "x" * 181})


def test_merge_changes_style_but_preserves_prompt_semantics_and_composition():
    prompt_direction = _direction()
    merged = merge_reference_art_direction(prompt_direction, _analysis())
    assert merged.scene_description == prompt_direction.scene_description
    assert merged.characters == prompt_direction.characters
    assert merged.objects == prompt_direction.objects
    assert merged.composition.startswith(prompt_direction.composition)
    assert _analysis().composition_tendency in merged.composition
    assert merged.background_description.startswith(prompt_direction.background_description)
    assert "do not add reference-scene objects" in merged.background_description
    assert merged.timeline_beats == prompt_direction.timeline_beats
    assert merged.palette == ["#101a3a", "#6655aa", "#ffd166", "#f4a6c1"]
    assert "zaobljene" in merged.shape_language
    assert "Robot" not in merged.visual_style


def test_reference_analysis_uses_multimodal_part_and_prompt_only_stays_compatible():
    async def run():
        provider = GenerativeSvgProvider(client=SimpleNamespace())
        calls = []

        async def response(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(parsed={"reference_analysis": _analysis().model_dump()}, text="")

        provider._gemini._generate_content = response
        prepared = prepare_reference_image(_image_bytes("PNG"))
        result = await provider.analyze_reference(prepared)
        assert result.mood.startswith("Nežno")
        content = calls[0]["contents"]
        assert len(content.parts) == 2
        assert content.parts[1].inline_data.mime_type == prepared.mime_type
        assert content.parts[1].inline_data.data == prepared.data

        prompt_provider = GenerativeSvgProvider(client=SimpleNamespace())
        prompt_calls = []

        async def prompt_response(**kwargs):
            prompt_calls.append(kwargs)
            return SimpleNamespace(parsed={"art_direction": _direction().model_dump()}, text="")

        prompt_provider._gemini._generate_content = prompt_response
        direction = await prompt_provider.generate_art_direction("Robot kuva čaj")
        assert direction == _direction()
        assert len(prompt_calls) == 1
        assert isinstance(prompt_calls[0]["contents"], str)

    asyncio.run(run())
