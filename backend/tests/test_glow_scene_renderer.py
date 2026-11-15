import xml.etree.ElementTree as ET

import pytest

from app.providers.generative_svg import merge_reference_art_direction
from app.renderers.glow_scene_renderer import MAX_PRIMARY_SUBJECTS, render_glow_scene
from app.renderers.svg_quality import validate_svg_quality
from app.renderers.svg_sanitizer import SVG_NS, sanitize_svg
from app.schemas.generative_svg import ArtDirection, ReferenceArtAnalysis


def _direction(*, characters, scene="Noćno zvezdano nebo", objects=None, palette=None) -> ArtDirection:
    return ArtDirection.model_validate({
        "title": "Glow scena", "duration_seconds": 10,
        "scene_description": scene,
        "characters": characters,
        "objects": objects or [], "background_description": scene,
        "composition": "Uravnotežena kompozicija", "visual_style": "Meki glow",
        "shape_language": "Zaobljeno", "palette": palette or ["#101a3a", "#4f9cff", "#ffd166"],
        "lighting": "Atmosferski sjaj", "line_treatment": "Meke linije", "depth_style": "Tri sloja",
        "mood": "Sanjivo", "motion_style": "Blago lebdenje",
        "timeline_beats": [{"start": 0, "duration": 10, "description": "Cela scena", "motion": "Lebdenje"}],
    })


CHILD = {"name": "Devojčica", "role": "posmatrač", "appearance": "meki zaobljeni lik"}
DOG = {"name": "Pas", "role": "pratilac", "appearance": "mali zaobljeni pas"}
ROBOT = {"name": "Robot", "role": "kuvar", "appearance": "mali plavi robot"}
CREATURE = {"name": "Plavo biće", "role": "putnik", "appearance": "mali blob maskota"}


def _sanitized(direction: ArtDirection):
    rendered = render_glow_scene(direction)
    return rendered, sanitize_svg(rendered.svg, duration_seconds=direction.duration_seconds)


def test_child_and_dog_scene_is_recognizable_sanitized_and_quality_safe():
    rendered, sanitized = _sanitized(_direction(characters=[CHILD, DOG]))
    assert rendered.subject_families == ("child", "animal")
    assert "child-root-1" in sanitized.content and "animal-root-2" in sanitized.content
    assert "star-field" in sanitized.content
    assert validate_svg_quality(sanitized).passed


def test_robot_kitchen_scene_contains_robot_and_tea_context():
    rendered, sanitized = _sanitized(_direction(
        characters=[ROBOT], scene="Robot pravi čaj u maloj kuhinji.",
        objects=[{"name": "Čajnik", "description": "čajnik i šolja na radnoj ploči"}],
    ))
    assert rendered.subject_families == ("robot",)
    assert "robot-root-1" in sanitized.content
    assert sanitized.element_count >= 15
    assert validate_svg_quality(sanitized).passed


def test_scene_semantics_resolve_opaque_character_names():
    direction = _direction(
        characters=[
            {"name": "Mila", "role": "posmatrač", "appearance": "meki lik"},
            {"name": "Bobi", "role": "pratilac", "appearance": "zaobljeni lik"},
        ],
        scene="Devojčica i pas gledaju zvezde.",
    )
    assert render_glow_scene(direction).subject_families == ("child", "animal")
    robot = _direction(
        characters=[{"name": "Bolti", "role": "kuvar", "appearance": "zaobljeni pomoćnik"}],
        scene="Robot pravi čaj u maloj kuhinji.",
    )
    assert render_glow_scene(robot).subject_families == ("robot",)


def test_short_serbian_animal_term_does_not_match_english_past():
    direction = _direction(
        characters=[{"name": "Bolti", "role": "automaton", "appearance": "rounded helper"}],
        scene="Robot makes tea while sparkles drift past the kitchen window.",
    )
    assert render_glow_scene(direction).subject_families == ("robot",)


def test_teardrop_description_does_not_add_tea_props():
    direction = _direction(
        characters=[CHILD, DOG],
        scene="Girl and puppy watch teardrop shooting stars at night.",
    )
    rendered, sanitized = _sanitized(direction)
    assert rendered.subject_families == ("child", "animal")
    assert 'x="930" y="430"' not in sanitized.content
    assert sanitized.element_count <= 100


def test_creature_space_scene_contains_blob_and_stardust_trail():
    rendered, sanitized = _sanitized(_direction(
        characters=[CREATURE], scene="Malo plavo biće leti kroz svemir i ostavlja trag zvezda.",
    ))
    assert rendered.subject_families == ("creature",)
    assert "creature-root-1" in sanitized.content and "stardust-trail" in sanitized.content
    assert validate_svg_quality(sanitized).passed


@pytest.mark.parametrize("count", [1, 2, 3])
def test_one_two_three_subject_layouts_are_bounded_and_balanced(count):
    rendered, sanitized = _sanitized(_direction(characters=[CREATURE] * count))
    assert len(rendered.subject_families) == count
    assert validate_svg_quality(sanitized).passed
    root = ET.fromstring(sanitized.content)
    subject_roots = [element for element in root.iter(f"{{{SVG_NS}}}g") if "root" in element.get("id", "")]
    assert len(subject_roots) == count


def test_renderer_caps_primary_subjects_and_element_count():
    rendered, sanitized = _sanitized(_direction(characters=[CREATURE] * 6))
    assert len(rendered.subject_families) == MAX_PRIMARY_SUBJECTS
    assert sanitized.element_count <= 100


def test_motion_is_bounded_and_never_independently_translates_anatomy():
    rendered, sanitized = _sanitized(_direction(characters=[CHILD, DOG, ROBOT]))
    assert sanitized.css_keyframes == 6
    assert "translateY(-16px)" in sanitized.content
    assert "translate(10px,-8px)" in sanitized.content
    assert ".head" not in sanitized.content and ".arm" not in sanitized.content and ".leg" not in sanitized.content
    assert validate_svg_quality(sanitized).passed


def test_reference_palette_changes_renderer_without_copying_subjects():
    reference = ReferenceArtAnalysis.model_validate({
        "dominant_palette": ["#220044", "#aa66ff"], "secondary_palette": ["#ffeeaa"],
        "contrast_level": "soft", "lighting_style": "dreamy glow", "shape_language": "round",
        "line_treatment": "thin", "texture_feel": "smooth", "depth_style": "layered",
        "composition_tendency": "diagonal", "mood": "dreamy", "softness": "high",
        "visual_complexity": "medium", "background_character": "atmospheric",
        "character_style_notes": "soft blobs", "motion_style_suggestion": "slow float",
        "confidence_notes": "high",
    })
    direction = _direction(characters=[CHILD, DOG])
    merged = merge_reference_art_direction(direction, reference)
    rendered = render_glow_scene(merged)
    assert "#220044" in rendered.svg and "#aa66ff" in rendered.svg
    assert rendered.subject_families == ("child", "animal")


def test_renderer_output_is_deterministic_for_same_direction():
    direction = _direction(characters=[CHILD, DOG])
    assert render_glow_scene(direction).svg == render_glow_scene(direction).svg


def test_premium_scene_has_layered_backgrounds_particles_and_parallax():
    _, sanitized = _sanitized(_direction(characters=[CHILD, DOG]))
    assert "atmosphereGlow" in sanitized.content and "haloGlow" in sanitized.content
    assert "star-field-distant" in sanitized.content and "star-field-mid" in sanitized.content
    assert "depth-back" in sanitized.content and "depth-mid" in sanitized.content
    assert "depth-front" in sanitized.content
    assert sanitized.css_keyframes == 6


def test_characters_use_gradients_highlights_shadows_and_reusable_glow_filters():
    _, sanitized = _sanitized(_direction(characters=[CHILD, DOG]))
    assert "subject1" in sanitized.content and "subject2" in sanitized.content
    assert "url(#subject1)" in sanitized.content
    assert 'fill="#ffffff" opacity=".16"' in sanitized.content
    for identifier in ("softGlow", "softShadow", "rimGlow", "trailGlow"):
        assert f'id="{identifier}"' in sanitized.content
    assert sanitized.element_count <= 100


def test_particle_field_is_deterministic_and_varies_size_and_opacity():
    direction = _direction(characters=[CREATURE], scene="Biće leti kroz svemir i zvezde.")
    first = render_glow_scene(direction).svg
    second = render_glow_scene(direction).svg
    assert first == second
    assert 'r="1"' in first or 'r="2"' in first
    assert 'opacity=".28"' in first or 'opacity=".38"' in first
