from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from app.schemas.generative_svg import ArtCharacter, ArtDirection

SVG_NS = "http://www.w3.org/2000/svg"
MAX_PRIMARY_SUBJECTS = 3
SUBJECT_POSITIONS = {
    1: ((640, 390),),
    2: ((430, 405), (850, 405)),
    3: ((380, 430), (640, 320), (900, 430)),
}
DEFAULT_PALETTE = ("#0b1638", "#263b78", "#69d7ff", "#ffd86b", "#f7f3ff")
_COLOR_NAMES = {
    "plava": "#4f9cff", "blue": "#4f9cff", "žuta": "#ffd86b", "zuta": "#ffd86b",
    "yellow": "#ffd86b", "ljubičasta": "#9d7cff", "ljubicasta": "#9d7cff",
    "purple": "#9d7cff", "roze": "#ff91c8", "pink": "#ff91c8", "bela": "#f7f3ff",
    "white": "#f7f3ff", "zelena": "#68d6a3", "green": "#68d6a3", "crvena": "#ff6b78",
    "red": "#ff6b78", "narandžasta": "#ff9f5a", "narandzasta": "#ff9f5a", "orange": "#ff9f5a",
}


@dataclass(frozen=True)
class GlowSceneRender:
    svg: str
    subject_families: tuple[str, ...]
    scene_family: str


def render_glow_scene(direction: ArtDirection) -> GlowSceneRender:
    palette = _palette(direction.palette)
    scene_text = _normalized(" ".join([
        direction.title, direction.scene_description, direction.background_description,
        direction.composition, direction.motion_style,
        *(f"{beat.description} {beat.motion}" for beat in direction.timeline_beats),
        *(f"{item.name} {item.description}" for item in direction.objects),
    ]))
    subjects = _subjects(direction, scene_text)[:MAX_PRIMARY_SUBJECTS]
    scene_family = "characters" if subjects else _scene_family(scene_text, bool(direction.objects))
    positions = _subject_positions(direction, scene_text, len(subjects)) if subjects else ()

    ET.register_namespace("", SVG_NS)
    root = ET.Element(_tag("svg"), {
        "width": "1280", "height": "720", "viewBox": "0 0 1280 720",
        "version": "1.1",
    })
    defs = ET.SubElement(root, _tag("defs"))
    _gradient(defs, "sky", palette[0], palette[1])
    _gradient(defs, "subjectGlow", palette[2], palette[3])
    _radial_gradient(defs, "atmosphereGlow", palette[2], palette[0])
    _radial_gradient(defs, "haloGlow", palette[4], palette[2])
    glow = ET.SubElement(defs, _tag("filter"), {"id": "softGlow", "x": "-30%", "y": "-30%", "width": "160%", "height": "160%"})
    ET.SubElement(glow, _tag("feDropShadow"), {"dx": "0", "dy": "0", "stdDeviation": "9", "flood-color": palette[2], "flood-opacity": ".72"})
    shadow = ET.SubElement(defs, _tag("filter"), {"id": "softShadow", "x": "-30%", "y": "-30%", "width": "160%", "height": "160%"})
    ET.SubElement(shadow, _tag("feDropShadow"), {"dx": "0", "dy": "8", "stdDeviation": "9", "flood-color": palette[0], "flood-opacity": ".45"})
    rim = ET.SubElement(defs, _tag("filter"), {"id": "rimGlow", "x": "-30%", "y": "-30%", "width": "160%", "height": "160%"})
    ET.SubElement(rim, _tag("feDropShadow"), {"dx": "0", "dy": "0", "stdDeviation": "5", "flood-color": palette[4], "flood-opacity": ".42"})
    trail = ET.SubElement(defs, _tag("filter"), {"id": "trailGlow", "x": "-40%", "y": "-40%", "width": "180%", "height": "180%"})
    ET.SubElement(trail, _tag("feDropShadow"), {"dx": "0", "dy": "0", "stdDeviation": "6", "flood-color": palette[3], "flood-opacity": ".65"})
    style = ET.SubElement(root, _tag("style"))
    style.text = _scene_style(bool(subjects), scene_text)

    ET.SubElement(root, _tag("rect"), {"width": "1280", "height": "720", "fill": "url(#sky)"})
    ET.SubElement(root, _tag("ellipse"), {"cx": "275", "cy": "180", "rx": "360", "ry": "245", "fill": "url(#atmosphereGlow)", "opacity": ".24", "class": "depth-back"})
    ET.SubElement(root, _tag("ellipse"), {"cx": "1030", "cy": "330", "rx": "330", "ry": "260", "fill": "url(#haloGlow)", "opacity": ".12", "class": "depth-mid"})
    _atmosphere(root, scene_text, palette)
    _environment(root, scene_text, palette)
    _render_storyboard_objects(root, scene_text, direction, palette)

    families: list[str] = []
    for index, ((family, character), (x, y)) in enumerate(zip(subjects, positions, strict=True), start=1):
        families.append(family)
        subject_color = palette[(index + 1) % len(palette)]
        accent = palette[(index + 2) % len(palette)]
        _gradient(defs, f"subject{index}", subject_color, accent)
        ET.SubElement(root, _tag("ellipse"), {
            "cx": str(x), "cy": str(y + 45), "rx": "125", "ry": "135",
            "fill": "url(#haloGlow)", "opacity": ".13", "filter": "url(#softGlow)",
        })
        _render_subject(root, family, character, index, x, y, subject_color, accent, _motion_preset(scene_text, index))

    if not subjects:
        _render_non_character(root, scene_family, scene_text, palette)

    _foreground(root, scene_text, palette)
    return GlowSceneRender(ET.tostring(root, encoding="unicode"), tuple(families), scene_family)


def _tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _gradient(parent: ET.Element, identifier: str, first: str, second: str) -> None:
    gradient = ET.SubElement(parent, _tag("linearGradient"), {"id": identifier, "x1": "0", "y1": "0", "x2": "1", "y2": "1"})
    ET.SubElement(gradient, _tag("stop"), {"offset": "0", "stop-color": first})
    ET.SubElement(gradient, _tag("stop"), {"offset": "1", "stop-color": second})


def _radial_gradient(parent: ET.Element, identifier: str, center: str, edge: str) -> None:
    gradient = ET.SubElement(parent, _tag("radialGradient"), {"id": identifier, "cx": ".5", "cy": ".5", "r": ".5"})
    ET.SubElement(gradient, _tag("stop"), {"offset": "0", "stop-color": center, "stop-opacity": ".9"})
    ET.SubElement(gradient, _tag("stop"), {"offset": ".58", "stop-color": center, "stop-opacity": ".28"})
    ET.SubElement(gradient, _tag("stop"), {"offset": "1", "stop-color": edge, "stop-opacity": "0"})


def _palette(values: list[str]) -> tuple[str, ...]:
    colors: list[str] = []
    for value in values:
        normalized = value.strip().casefold()
        if re.fullmatch(r"#[0-9a-f]{6}", normalized):
            color = normalized
        elif re.fullmatch(r"#[0-9a-f]{3}", normalized):
            color = "#" + "".join(character * 2 for character in normalized[1:])
        else:
            color = next((mapped for name, mapped in _COLOR_NAMES.items() if name in normalized), "")
        if color and color not in colors:
            colors.append(color)
    for fallback in DEFAULT_PALETTE:
        if len(colors) >= 5:
            break
        if fallback not in colors:
            colors.append(fallback)
    return tuple(colors)


def _normalized(value: str) -> str:
    return value.casefold().translate(str.maketrans("čćžšđ", "cczsd"))


def _subjects(direction: ArtDirection, scene_text: str) -> list[tuple[str, ArtCharacter | None]]:
    result = [(_family(_normalized(f"{item.name} {item.role} {item.appearance}")), item) for item in direction.characters]
    expected = _scene_families(scene_text)
    assigned = {family for family, _ in result if family != "generic"}
    missing = [family for family in expected if family not in assigned]
    if result:
        reconciled: list[tuple[str, ArtCharacter | None]] = []
        for family, character in result:
            if family == "generic" and missing:
                family = missing.pop(0)
            if family != "generic":
                reconciled.append((family, character))
        result = reconciled
    if not result:
        result.extend((family, None) for family in expected)
    return result


def _scene_family(scene_text: str, has_objects: bool) -> str:
    checks = (
        ("building", ("zgrad", "building", "neboder", "skyscraper", "toranj", "tower", "architecture", "arhitektur")),
        ("city", ("grad", "city", "skyline", "urban", "metropol")),
        ("vehicle", ("automobil", "auto", "car", "vehicle", "vozilo", "motor", "train", "voz", "bicikl")),
        ("landscape", ("planin", "mountain", "magl", "mist", "landscape", "prirod", "nature", "suma", "forest", "jezer", "lake", "more", "ocean")),
        ("product", ("product", "proizvod", "predmet", "object", "telefon", "phone", "boca", "bottle", "sat", "watch", "stolica", "chair")),
    )
    for family, terms in checks:
        if _has_any(scene_text, terms):
            return family
    return "product" if has_objects else "abstract"


def _scene_families(scene_text: str) -> list[str]:
    families: list[str] = []
    checks = (
        ("child", ("devoj", "girl", "dete", "child", "boy", "decak")),
        ("animal", ("pas", "dog", "puppy", "pup", "canine", "mack", "cat", "animal", "zivot")),
        ("robot", ("robot", "android", "droid")),
        ("creature", ("bice", "creature", "mascot", "vanzemalj")),
    )
    for family, terms in checks:
        if _has_any(scene_text, terms):
            families.append(family)
    return families


def _family(text: str) -> str:
    if _has_any(text, ("robot", "android", "droid", "automaton")):
        return "robot"
    if _has_any(text, ("pas", "dog", "puppy", "pup", "canine", "mack", "cat", "animal", "zivot")):
        return "animal"
    if _has_any(text, ("devoj", "girl", "dete", "child", "boy", "decak")):
        return "child"
    if _has_any(text, ("person", "woman", "man", "zena", "muskar", "adult")):
        return "person"
    if _has_any(text, ("bice", "creature", "mascot", "vanzemalj")):
        return "creature"
    return "generic"


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    tokens = re.findall(r"[a-z0-9]+", text)
    exact = {"pas", "dog", "cat", "pup", "boy", "girl", "man", "tea", "grad", "city", "car", "auto"}
    return any(
        token == term if term in exact else token.startswith(term)
        for term in terms
        for token in tokens
    )


def _subject_positions(direction: ArtDirection, scene: str, count: int) -> tuple[tuple[int, int], ...]:
    if count != 1:
        return SUBJECT_POSITIONS[count]
    if _has_any(scene, ("upper-left", "upper left", "gornj", "ulazi", "enter")):
        return ((300, 335),)
    if _has_any(scene, ("planet", "planeta", "right balance", "desno", "orbit", "prolazi", "pass")):
        return ((355, 395),)
    if _has_any(scene, ("meteor", "comet", "observe", "ugleda", "vidi", "stop")):
        return ((390, 405),)
    if _has_any(scene, ("land", "sleti", "descend", "landing", "moon", "mesec")):
        return ((640, 390),)
    return SUBJECT_POSITIONS[1]


def _motion_preset(scene: str, index: int) -> str:
    if _has_any(scene, ("land", "sleti", "descend", "landing")):
        return "subject-land"
    if _has_any(scene, ("meteor", "comet", "kometa")):
        return "subject-observe"
    if _has_any(scene, ("pass", "past", "prolazi", "orbit", "kruzi", "curving")):
        return "subject-pass"
    if _has_any(scene, ("observe", "ugleda", "vidi", "sees", "stop", "posmatra", "dodge")):
        return "subject-observe"
    if _has_any(scene, ("enter", "ulazi", "glide", "travels", "putuje", "flying", "forward")):
        return "subject-enter"
    return ("subject-float", "subject-bounce", "subject-drift")[index % 3]


def _render_subject(
    root: ET.Element, family: str, character: ArtCharacter | None, index: int,
    x: int, y: int, color: str, accent: str, motion: str,
) -> None:
    identifier = f"{family}-root-{index}"
    ET.SubElement(root, _tag("ellipse"), {"cx": str(x), "cy": str(y + 132), "rx": "88", "ry": "18", "fill": "#0b1638", "opacity": ".28"})
    group = ET.SubElement(root, _tag("g"), {"id": identifier, "class": motion, "filter": "url(#rimGlow)"})
    primary_fill = f"url(#subject{index})"
    if family in {"child", "person"}:
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x), "cy": str(y + 42), "rx": "72", "ry": "92", "fill": primary_fill})
        ET.SubElement(group, _tag("circle"), {"cx": str(x), "cy": str(y - 45), "r": "58", "fill": primary_fill})
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x - 25), "cy": str(y + 18), "rx": "22", "ry": "58", "fill": "#ffffff", "opacity": ".12"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x - 31), "cy": str(y - 78), "r": "12", "fill": "#ffffff", "opacity": ".16"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x - 19), "cy": str(y - 52), "r": "7", "fill": "#172342", "class": "eye-blink"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 19), "cy": str(y - 52), "r": "7", "fill": "#172342", "class": "eye-blink"})
        ET.SubElement(group, _tag("path"), {"d": f"M{x-18} {y-22} Q{x} {y-8} {x+18} {y-22}", "fill": "none", "stroke": "#172342", "stroke-width": "5", "stroke-linecap": "round"})
    elif family == "animal":
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x - 18), "cy": str(y + 35), "rx": "90", "ry": "62", "fill": primary_fill})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 55), "cy": str(y - 5), "r": "55", "fill": primary_fill})
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x - 42), "cy": str(y + 16), "rx": "38", "ry": "18", "fill": "#ffffff", "opacity": ".13"})
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x + 30), "cy": str(y - 48), "rx": "18", "ry": "30", "fill": accent, "transform": f"rotate(-20 {x+30} {y-48})"})
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x + 77), "cy": str(y - 48), "rx": "18", "ry": "30", "fill": accent, "transform": f"rotate(20 {x+77} {y-48})"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 42), "cy": str(y - 12), "r": "6", "fill": "#172342", "class": "eye-blink"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 70), "cy": str(y - 12), "r": "6", "fill": "#172342", "class": "eye-blink"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 57), "cy": str(y + 7), "r": "7", "fill": "#172342"})
        ET.SubElement(group, _tag("path"), {"d": f"M{x-100} {y+32} Q{x-145} {y-12} {x-118} {y-45}", "fill": "none", "stroke": color, "stroke-width": "22", "stroke-linecap": "round"})
    elif family == "robot":
        ET.SubElement(group, _tag("rect"), {"x": str(x - 72), "y": str(y - 25), "width": "144", "height": "145", "rx": "52", "fill": primary_fill})
        ET.SubElement(group, _tag("rect"), {"x": str(x - 65), "y": str(y - 105), "width": "130", "height": "95", "rx": "38", "fill": primary_fill})
        ET.SubElement(group, _tag("rect"), {"x": str(x - 48), "y": str(y - 90), "width": "34", "height": "65", "rx": "17", "fill": "#ffffff", "opacity": ".16"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x - 25), "cy": str(y - 60), "r": "10", "fill": "#172342", "class": "eye-blink"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 25), "cy": str(y - 60), "r": "10", "fill": "#172342", "class": "eye-blink"})
        ET.SubElement(group, _tag("line"), {"x1": str(x), "y1": str(y - 105), "x2": str(x), "y2": str(y - 130), "stroke": accent, "stroke-width": "8", "stroke-linecap": "round"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x), "cy": str(y - 138), "r": "9", "fill": "#ffd86b", "class": "glow-pulse"})
    else:
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x), "cy": str(y), "rx": "105", "ry": "118", "fill": "url(#subjectGlow)"})
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x - 34), "cy": str(y - 28), "rx": "32", "ry": "62", "fill": "#ffffff", "opacity": ".16"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x - 32), "cy": str(y - 18), "r": "13", "fill": "#f7f3ff", "class": "eye-blink"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 32), "cy": str(y - 18), "r": "13", "fill": "#f7f3ff", "class": "eye-blink"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x - 30), "cy": str(y - 16), "r": "6", "fill": "#172342"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x + 30), "cy": str(y - 16), "r": "6", "fill": "#172342"})
        ET.SubElement(group, _tag("path"), {"d": f"M{x-22} {y+24} Q{x} {y+42} {x+22} {y+24}", "fill": "none", "stroke": "#f7f3ff", "stroke-width": "6", "stroke-linecap": "round"})


def _render_storyboard_objects(root: ET.Element, scene: str, direction: ArtDirection, palette: tuple[str, ...]) -> None:
    object_text = _normalized(" ".join(f"{item.name} {item.description}" for item in direction.objects))
    combined = f"{scene} {object_text}"
    if _has_any(combined, ("ringed", "prsten", "saturn")):
        group = ET.SubElement(root, _tag("g"), {"id": "ringed-planet", "class": "depth-back", "filter": "url(#softGlow)"})
        ET.SubElement(group, _tag("ellipse"), {"cx": "940", "cy": "330", "rx": "225", "ry": "62", "fill": "none", "stroke": palette[3], "stroke-width": "20", "stroke-opacity": ".7", "transform": "rotate(-14 940 330)"})
        ET.SubElement(group, _tag("circle"), {"cx": "940", "cy": "330", "r": "132", "fill": "url(#subjectGlow)"})
        ET.SubElement(group, _tag("ellipse"), {"cx": "905", "cy": "292", "rx": "52", "ry": "30", "fill": palette[4], "opacity": ".2"})
    if _has_any(combined, ("glowing_meteor", "glowing meteor", "meteor", "comet", "kometa")):
        group = ET.SubElement(root, _tag("g"), {"id": "glowing-meteor", "class": "meteor-streak", "filter": "url(#trailGlow)"})
        ET.SubElement(group, _tag("path"), {"d": "M1180 105 L790 300", "stroke": palette[3], "stroke-width": "28", "stroke-linecap": "round", "stroke-opacity": ".18"})
        ET.SubElement(group, _tag("path"), {"d": "M1150 120 L850 270", "stroke": palette[4], "stroke-width": "12", "stroke-linecap": "round", "stroke-opacity": ".72"})
        ET.SubElement(group, _tag("circle"), {"cx": "825", "cy": "282", "r": "34", "fill": palette[3]})
    if _has_any(combined, ("tiny", "moon", "mesec", "lunar")):
        group = ET.SubElement(root, _tag("g"), {"id": "tiny-moon-surface"})
        ET.SubElement(group, _tag("path"), {"d": "M110 720 Q640 430 1170 720 Z", "fill": "url(#subjectGlow)", "filter": "url(#rimGlow)"})
        for x, y, radius in ((390, 625, 34), (680, 580, 25), (900, 650, 44)):
            ET.SubElement(group, _tag("ellipse"), {"cx": str(x), "cy": str(y), "rx": str(radius), "ry": str(max(12, radius // 2)), "fill": palette[1], "opacity": ".32"})


def _render_non_character(root: ET.Element, family: str, scene: str, palette: tuple[str, ...]) -> None:
    if family == "building":
        _render_building(root, palette)
    elif family == "city":
        _render_city(root, palette)
    elif family == "vehicle":
        _render_vehicle(root, palette)
    elif family == "landscape":
        _render_landscape(root, palette)
    elif family == "product":
        _render_product(root, palette)
    else:
        _render_abstract(root, palette)


def _render_building(root: ET.Element, palette: tuple[str, ...]) -> None:
    skyline = ET.SubElement(root, _tag("g"), {"id": "distant-skyline", "class": "depth-back", "opacity": ".34"})
    for index, (x, width, height) in enumerate(((90, 120, 190), (225, 85, 260), (960, 105, 235), (1080, 125, 170))):
        ET.SubElement(skyline, _tag("rect"), {"x": str(x), "y": str(585 - height), "width": str(width), "height": str(height), "rx": "10", "fill": palette[index % len(palette)]})
    group = ET.SubElement(root, _tag("g"), {"id": "building-scene", "filter": "url(#rimGlow)"})
    ET.SubElement(group, _tag("rect"), {"x": "405", "y": "575", "width": "470", "height": "62", "rx": "16", "fill": palette[1]})
    ET.SubElement(group, _tag("polygon"), {"points": "475,145 790,115 810,575 455,575", "fill": "url(#subjectGlow)"})
    ET.SubElement(group, _tag("polygon"), {"points": "790,115 865,175 875,575 810,575", "fill": palette[1], "opacity": ".82"})
    ET.SubElement(group, _tag("polygon"), {"points": "475,145 790,115 760,155 500,180", "fill": palette[4], "opacity": ".2"})
    windows = ET.SubElement(group, _tag("g"), {"id": "building-windows"})
    for row in range(5):
        for column in range(3):
            ET.SubElement(windows, _tag("rect"), {
                "x": str(520 + column * 82), "y": str(205 + row * 65), "width": "48", "height": "30", "rx": "5",
                "fill": palette[3 if (row + column) % 3 else 4], "opacity": str(.48 + ((row + column) % 3) * .16),
                "class": "sparkle" if (row + column) % 4 == 0 else "",
            })
    ET.SubElement(group, _tag("rect"), {"x": "615", "y": "500", "width": "86", "height": "75", "rx": "12", "fill": palette[0], "opacity": ".78"})
    ET.SubElement(group, _tag("line"), {"x1": "658", "y1": "505", "x2": "658", "y2": "570", "stroke": palette[4], "stroke-width": "3", "stroke-opacity": ".42"})
    ET.SubElement(root, _tag("ellipse"), {"cx": "650", "cy": "635", "rx": "290", "ry": "28", "fill": palette[2], "opacity": ".14", "class": "depth-front"})


def _render_city(root: ET.Element, palette: tuple[str, ...]) -> None:
    group = ET.SubElement(root, _tag("g"), {"id": "city-skyline", "class": "depth-mid"})
    buildings = ((90, 165, 230), (245, 145, 330), (390, 180, 265), (565, 150, 390), (710, 190, 285), (895, 135, 350), (1020, 170, 245))
    for index, (x, width, height) in enumerate(buildings):
        ET.SubElement(group, _tag("rect"), {"x": str(x), "y": str(610 - height), "width": str(width), "height": str(height), "rx": "12", "fill": palette[index % min(len(palette), 4)], "opacity": ".78"})
        for row in range(3):
            ET.SubElement(group, _tag("rect"), {"x": str(x + 28), "y": str(610 - height + 45 + row * 55), "width": str(max(width - 56, 22)), "height": "12", "rx": "4", "fill": palette[4], "opacity": ".26"})


def _render_vehicle(root: ET.Element, palette: tuple[str, ...]) -> None:
    ET.SubElement(root, _tag("path"), {"d": "M60 585 Q640 505 1220 585 L1220 675 L60 675 Z", "fill": palette[0], "opacity": ".78"})
    ET.SubElement(root, _tag("path"), {"d": "M100 605 Q640 540 1180 605", "fill": "none", "stroke": palette[4], "stroke-width": "5", "stroke-opacity": ".24", "stroke-dasharray": "28 38", "class": "depth-front"})
    group = ET.SubElement(root, _tag("g"), {"id": "vehicle-scene", "filter": "url(#rimGlow)"})
    ET.SubElement(group, _tag("path"), {"d": "M370 480 Q410 410 505 390 L760 390 Q850 410 910 480 L980 500 Q1015 510 1015 550 L1015 585 L285 585 L285 535 Q290 500 345 490 Z", "fill": "url(#subjectGlow)"})
    ET.SubElement(group, _tag("path"), {"d": "M500 405 L590 330 L760 345 L840 405 Z", "fill": palette[1], "opacity": ".82"})
    ET.SubElement(group, _tag("path"), {"d": "M520 397 L603 345 L665 350 L665 397 Z M680 350 L750 358 L818 397 L680 397 Z", "fill": palette[4], "opacity": ".3"})
    for x in (430, 870):
        ET.SubElement(group, _tag("circle"), {"cx": str(x), "cy": "585", "r": "56", "fill": "#111827"})
        ET.SubElement(group, _tag("circle"), {"cx": str(x), "cy": "585", "r": "27", "fill": palette[4], "opacity": ".65"})
    ET.SubElement(group, _tag("ellipse"), {"cx": "955", "cy": "515", "rx": "26", "ry": "14", "fill": palette[3], "filter": "url(#trailGlow)", "class": "glow-pulse"})
    ET.SubElement(root, _tag("ellipse"), {"cx": "650", "cy": "638", "rx": "400", "ry": "35", "fill": palette[2], "opacity": ".13"})


def _render_landscape(root: ET.Element, palette: tuple[str, ...]) -> None:
    ET.SubElement(root, _tag("circle"), {"cx": "960", "cy": "205", "r": "72", "fill": palette[3], "filter": "url(#softGlow)", "class": "glow-pulse"})
    ET.SubElement(root, _tag("polygon"), {"points": "0,610 230,350 410,590 605,285 860,610", "fill": palette[1], "opacity": ".72", "class": "depth-back"})
    ET.SubElement(root, _tag("polygon"), {"points": "360,625 650,330 870,570 1030,385 1280,625", "fill": "url(#subjectGlow)", "opacity": ".74", "class": "depth-mid"})
    ET.SubElement(root, _tag("polygon"), {"points": "0,650 270,500 520,640 780,470 1010,630 1280,530 1280,720 0,720", "fill": palette[0], "opacity": ".86"})
    for x, y, rx in ((260, 455, 240), (700, 505, 300), (1080, 460, 225)):
        ET.SubElement(root, _tag("ellipse"), {"cx": str(x), "cy": str(y), "rx": str(rx), "ry": "48", "fill": palette[4], "opacity": ".13", "class": "depth-mid"})


def _render_product(root: ET.Element, palette: tuple[str, ...]) -> None:
    ET.SubElement(root, _tag("ellipse"), {"cx": "640", "cy": "590", "rx": "260", "ry": "54", "fill": palette[1], "opacity": ".72"})
    group = ET.SubElement(root, _tag("g"), {"id": "product-scene", "filter": "url(#rimGlow)"})
    ET.SubElement(group, _tag("rect"), {"x": "500", "y": "245", "width": "280", "height": "320", "rx": "74", "fill": "url(#subjectGlow)"})
    ET.SubElement(group, _tag("rect"), {"x": "530", "y": "275", "width": "55", "height": "240", "rx": "28", "fill": "#ffffff", "opacity": ".14"})
    ET.SubElement(group, _tag("ellipse"), {"cx": "640", "cy": "535", "rx": "96", "ry": "18", "fill": palette[0], "opacity": ".2"})


def _render_abstract(root: ET.Element, palette: tuple[str, ...]) -> None:
    group = ET.SubElement(root, _tag("g"), {"id": "abstract-scene", "class": "depth-mid", "filter": "url(#softGlow)"})
    shapes = ((410, 345, 170, 110, 2), (650, 305, 210, 145, 3), (850, 410, 150, 190, 4), (570, 500, 245, 95, 2))
    for x, y, rx, ry, color in shapes:
        ET.SubElement(group, _tag("ellipse"), {"cx": str(x), "cy": str(y), "rx": str(rx), "ry": str(ry), "fill": palette[color % len(palette)], "opacity": ".34"})
    ET.SubElement(group, _tag("path"), {"d": "M230 460 Q460 170 680 390 T1060 285", "fill": "none", "stroke": palette[4], "stroke-width": "18", "stroke-opacity": ".32", "stroke-linecap": "round"})


def _atmosphere(root: ET.Element, scene: str, palette: tuple[str, ...]) -> None:
    stars = _has_any(scene, ("zvezd", "star", "space", "svemir", "noc", "night"))
    if stars:
        distant = ET.SubElement(root, _tag("g"), {"id": "star-field-distant", "class": "depth-back"})
        mid = ET.SubElement(root, _tag("g"), {"id": "star-field-mid", "class": "depth-mid"})
        for index in range(18):
            seed = hashlib.sha256(f"star-{index}-{scene}".encode()).digest()
            x = 80 + int.from_bytes(seed[:2], "big") % 1120
            y = 55 + int.from_bytes(seed[2:4], "big") % 430
            radius = 1 + seed[4] % 5
            group = distant if index < 9 else mid
            ET.SubElement(group, _tag("circle"), {
                "cx": str(x), "cy": str(y), "r": str(radius),
                "fill": palette[3 if index % 3 else 4],
                "opacity": str(.28 + (seed[5] % 6) * .1),
                "class": "sparkle" if index >= 9 else "",
            })
        ET.SubElement(root, _tag("circle"), {"cx": "1080", "cy": "130", "r": "88", "fill": "url(#haloGlow)", "opacity": ".56", "class": "glow-pulse"})
        ET.SubElement(root, _tag("circle"), {"cx": "1080", "cy": "130", "r": "48", "fill": palette[4], "opacity": ".9", "class": "glow-pulse", "filter": "url(#softGlow)"})
        ET.SubElement(root, _tag("path"), {"d": "M190 240 Q420 190 650 245 T1110 230", "fill": "none", "stroke": palette[2], "stroke-width": "3", "stroke-opacity": ".18", "stroke-dasharray": "3 24", "class": "depth-mid"})
    else:
        for x, y, rx in ((180, 135, 110), (1040, 165, 135), (710, 105, 90)):
            ET.SubElement(root, _tag("ellipse"), {"cx": str(x), "cy": str(y), "rx": str(rx), "ry": "34", "fill": "url(#haloGlow)", "opacity": ".19", "class": "depth-back"})


def _environment(root: ET.Element, scene: str, palette: tuple[str, ...]) -> None:
    if _has_any(scene, ("kuhinj", "kitchen", "caj", "tea")):
        ET.SubElement(root, _tag("rect"), {"x": "110", "y": "115", "width": "260", "height": "310", "rx": "40", "fill": palette[0], "opacity": ".38"})
        ET.SubElement(root, _tag("rect"), {"x": "150", "y": "155", "width": "180", "height": "210", "rx": "28", "fill": "url(#atmosphereGlow)", "opacity": ".42"})
        ET.SubElement(root, _tag("rect"), {"x": "900", "y": "150", "width": "250", "height": "220", "rx": "36", "fill": palette[1], "opacity": ".32"})
        ET.SubElement(root, _tag("line"), {"x1": "1025", "y1": "165", "x2": "1025", "y2": "355", "stroke": palette[4], "stroke-width": "4", "stroke-opacity": ".16"})
        ET.SubElement(root, _tag("rect"), {"x": "70", "y": "545", "width": "1140", "height": "110", "rx": "35", "fill": palette[1], "opacity": ".9"})
        ET.SubElement(root, _tag("rect"), {"x": "930", "y": "430", "width": "145", "height": "105", "rx": "42", "fill": palette[3]})
        ET.SubElement(root, _tag("path"), {"d": "M1070 455 Q1140 470 1080 510", "fill": "none", "stroke": palette[3], "stroke-width": "22", "stroke-linecap": "round"})
        ET.SubElement(root, _tag("rect"), {"x": "780", "y": "485", "width": "85", "height": "62", "rx": "22", "fill": palette[4]})
        ET.SubElement(root, _tag("path"), {"d": "M800 480 Q780 445 805 420 M835 480 Q855 445 830 420", "fill": "none", "stroke": palette[4], "stroke-width": "7", "stroke-linecap": "round", "class": "depth-mid", "filter": "url(#trailGlow)"})
    elif _has_any(scene, ("space", "svemir", "leti", "fly")):
        ET.SubElement(root, _tag("ellipse"), {"cx": "410", "cy": "260", "rx": "310", "ry": "145", "fill": "url(#atmosphereGlow)", "opacity": ".24", "class": "depth-back"})
        ET.SubElement(root, _tag("ellipse"), {"cx": "930", "cy": "390", "rx": "280", "ry": "130", "fill": "url(#haloGlow)", "opacity": ".14", "class": "depth-mid"})
        trail = ET.SubElement(root, _tag("g"), {"id": "stardust-trail", "class": "depth-mid", "filter": "url(#trailGlow)"})
        for index in range(7):
            ET.SubElement(trail, _tag("circle"), {"cx": str(180 + index * 52), "cy": str(430 + (index % 2) * 18), "r": str(4 + index % 3), "fill": palette[3], "opacity": str(.35 + index * .08)})


def _foreground(root: ET.Element, scene: str, palette: tuple[str, ...]) -> None:
    ET.SubElement(root, _tag("ellipse"), {"cx": "640", "cy": "690", "rx": "610", "ry": "58", "fill": palette[0], "opacity": ".42"})
    ET.SubElement(root, _tag("ellipse"), {"cx": "220", "cy": "650", "rx": "245", "ry": "38", "fill": palette[2], "opacity": ".08", "class": "depth-front"})
    ET.SubElement(root, _tag("ellipse"), {"cx": "1040", "cy": "660", "rx": "280", "ry": "44", "fill": palette[3], "opacity": ".07", "class": "depth-front"})


_STYLE = """
@keyframes subjectFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
@keyframes subjectBounce{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-16px) scale(1.04)}}
@keyframes subjectDrift{0%,100%{transform:translate(0,0) rotate(0deg)}50%{transform:translate(10px,-8px) rotate(3deg)}}
@keyframes sparklePulse{0%,100%{opacity:.3;transform:scale(.8)}50%{opacity:1;transform:scale(1.15)}}
@keyframes eyeBlink{0%,88%,100%{transform:scaleY(1)}92%{transform:scaleY(.2)}}
@keyframes ambientDrift{0%,100%{transform:translateX(0)}50%{transform:translateX(10px)}}
.subject-float{animation:subjectFloat 6s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.subject-bounce{animation:subjectBounce 5s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.subject-drift{animation:subjectDrift 7s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.sparkle{animation:sparklePulse 3s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.eye-blink{animation:eyeBlink 5s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.glow-pulse{animation:sparklePulse 4s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.particle-drift{animation:ambientDrift 9s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.depth-back{animation:ambientDrift 15s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
.depth-mid{animation:ambientDrift 11s ease-in-out infinite reverse;transform-origin:center;transform-box:fill-box}
.depth-front{animation:ambientDrift 8s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
"""


_ACTION_STYLES = {
    "subject-enter": "@keyframes subjectEnter{0%{transform:translate(-42px,8px)}100%{transform:translate(10px,-5px)}}\n.subject-enter{animation:subjectEnter 5s ease-in-out infinite alternate;transform-origin:center;transform-box:fill-box}",
    "subject-pass": "@keyframes subjectPass{0%,100%{transform:translateX(-12px)}50%{transform:translate(28px,-8px)}}\n.subject-pass{animation:subjectPass 6s ease-in-out infinite;transform-origin:center;transform-box:fill-box}",
    "subject-observe": "@keyframes subjectObserve{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}\n.subject-observe{animation:subjectObserve 6s ease-in-out infinite;transform-origin:center;transform-box:fill-box}",
    "subject-land": "@keyframes subjectLand{0%{transform:translateY(-20px)}100%{transform:translateY(24px)}}\n.subject-land{animation:subjectLand 6s ease-out infinite alternate;transform-origin:center;transform-box:fill-box}",
}
_METEOR_STYLE = "@keyframes meteorStreak{0%,100%{transform:translate(22px,-12px);opacity:.75}50%{transform:translate(-18px,10px);opacity:1}}\n.meteor-streak{animation:meteorStreak 3s ease-in-out infinite;transform-origin:center;transform-box:fill-box}"


def _scene_style(has_characters: bool, scene: str) -> str:
    style = _STYLE if has_characters else "\n".join(
        line for line in _STYLE.splitlines()
        if not line.startswith("@keyframes eyeBlink") and not line.startswith(".eye-blink")
    )
    if has_characters:
        preset = _motion_preset(scene, 1)
        if preset in _ACTION_STYLES:
            style += "\n" + _ACTION_STYLES[preset]
    if _has_any(scene, ("meteor", "comet", "kometa")):
        style += "\n" + _METEOR_STYLE
    return style
