import hashlib
import re

from app.renderers.svg_quality import validate_svg_quality
from app.renderers.svg_sanitizer import sanitize_svg
from app.schemas.generative_svg import StoryboardPlan
from app.services.generative_svg_generation import render_storyboard_plan


def _space_storyboard() -> StoryboardPlan:
    shared = {
        "title": "Put kroz svemir", "duration_seconds": 10, "scene_description": "Malo plavo biće leti kroz svemir",
        "characters": [], "objects": [], "background_description": "Duboki svemir",
        "composition": "Srednji plan", "visual_style": "Meki glow", "shape_language": "Zaobljeno",
        "palette": ["#0b1638", "#3155a4", "#4f9cff", "#ffd86b", "#f7f3ff"],
        "lighting": "Plavi rubni sjaj", "line_treatment": "Meke linije", "depth_style": "Slojevito",
        "mood": "Sanjivo", "motion_style": "Blago lebdenje",
        "timeline_beats": [{"start": 0, "duration": 10, "description": "Putovanje", "motion": "Lebdenje"}],
    }
    subjects = [
        {"id": "blue_creature", "name": "Malo plavo biće", "kind": "creature", "appearance": "Meko plavo biće sa zlatnim sjajem"},
        {"id": "ringed_planet", "name": "Ringed planet", "kind": "object", "appearance": "Velika planeta sa prstenovima"},
        {"id": "glowing_meteor", "name": "Glowing meteor", "kind": "object", "appearance": "Sjajan meteor sa dugim tragom"},
        {"id": "tiny_moon", "name": "Tiny moon", "kind": "object", "appearance": "Mali mesec sa kraterima"},
    ]
    scene_data = (
        ("scene_1", ["blue_creature"], "Biće ulazi i putuje kroz otvoreni svemir", "upper-left entry", "enter and glide"),
        ("scene_2", ["blue_creature", "ringed_planet"], "Biće prolazi pored velike planete", "large background object right", "pass and orbit"),
        ("scene_3", ["blue_creature", "glowing_meteor"], "Biće ugleda meteor", "diagonal meteor path", "observe and stop"),
        ("scene_4", ["blue_creature", "tiny_moon"], "Biće sleće na mali mesec", "centered landing composition", "descend and land"),
    )
    return StoryboardPlan.model_validate({
        "title": "Put kroz svemir", "total_duration_seconds": 20,
        "shared_art_direction": shared, "recurring_subjects": subjects,
        "scenes": [{"id": scene_id, "duration_seconds": 5, "description": description, "environment": "Svemir", "subject_ids": ids, "action": action, "mood": "Sanjivo", "composition": composition, "transition_in": "fade", "transition_out": "crossfade"} for scene_id, ids, description, composition, action in scene_data],
    })


def test_storyboard_objects_actions_and_identity_are_realized_deterministically():
    plan = _space_storyboard()
    first = render_storyboard_plan(plan)
    second = render_storyboard_plan(plan)
    svgs = [item.response.svg for item in first]
    assert "ringed-planet" in svgs[1]
    assert "glowing-meteor" in svgs[2] and "meteor-streak" in svgs[2]
    assert "tiny-moon-surface" in svgs[3]
    assert "subject-enter" in svgs[0]
    assert "subject-pass" in svgs[1]
    assert "subject-observe" in svgs[2]
    assert "subject-land" in svgs[3]
    assert len({hashlib.sha256(svg.encode()).hexdigest() for svg in svgs}) == 4
    identity = [re.search(r'<linearGradient id="subject1".*?</linearGradient>', svg).group(0) for svg in svgs]
    assert len(set(identity)) == 1
    assert [item.response.svg for item in second] == svgs
    for item in first:
        sanitized = sanitize_svg(item.response.svg, duration_seconds=item.response.duration_seconds)
        assert validate_svg_quality(sanitized).passed
