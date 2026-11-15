from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from app.renderers.svg_sanitizer import SVG_NS, SanitizedSvg

SAFE_LEFT, SAFE_TOP, SAFE_RIGHT, SAFE_BOTTOM = 64.0, 36.0, 1216.0, 684.0

_CHARACTER_TERMS = {
    "character", "person", "child", "girl", "boy", "woman", "man", "adult",
    "dog", "cat", "animal", "robot", "creature",
}
_HEAD_TERMS = {"head", "face", "glava", "lice"}
_LIMB_TERMS = {
    "arm", "leg", "hand", "foot", "limb", "tail", "ear",
    "ruka", "noga", "saka", "stopalo", "rep", "uvo",
}
_ANATOMY_TERMS = _HEAD_TERMS | _LIMB_TERMS | {"body", "torso", "telo"}
_TOKEN_RE = re.compile(r"[a-zA-Z]+")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
_TRANSFORM_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")


@dataclass(frozen=True)
class SvgQualityIssue:
    code: str
    message: str


@dataclass(frozen=True)
class SvgQualityResult:
    passed: bool
    issues: tuple[SvgQualityIssue, ...]


def validate_svg_quality(svg: SanitizedSvg | str) -> SvgQualityResult:
    """Apply conservative structural checks to an already-sanitized SVG."""
    content = svg.content if isinstance(svg, SanitizedSvg) else svg
    root = ET.fromstring(content)
    parents = {child: parent for parent in root.iter() for child in parent}
    groups = [element for element in root.iter(f"{{{SVG_NS}}}g")]
    character_roots = [element for element in groups if _is_character_root(element, parents)]
    issues: list[SvgQualityIssue] = []
    animation_transforms = _animation_transforms(root)

    for character in character_roots:
        bounds = _known_bounds(character)
        transforms = [character.get("transform", "")]
        for class_name in character.get("class", "").split():
            transforms.extend(animation_transforms.get(class_name, ()))
        for transform in transforms:
            translation = _simple_translation(transform)
            if bounds is not None and translation is not None:
                left, top, right, bottom = bounds
                dx, dy = translation
                left, right, top, bottom = left + dx, right + dx, top + dy, bottom + dy
                if right <= 0 or bottom <= 0 or left >= 1280 or top >= 720:
                    _add_once(issues, "primary_subject_outside_safe_bounds", "Primary character is outside the viewport.")
                elif left < SAFE_LEFT or right > SAFE_RIGHT or top < SAFE_TOP or bottom > SAFE_BOTTOM:
                    _add_once(issues, "primary_subject_outside_safe_bounds", "Primary character is outside safe viewport bounds.")

    if character_roots:
        for group in groups:
            if _anatomy_kind(group) and not any(_is_descendant(group, root_group, parents) for root_group in character_roots):
                _add_once(issues, "detached_anatomical_group", "Character body parts are not grouped coherently.")

    for group in groups:
        kind = _anatomy_kind(group)
        if not kind or not any(_is_descendant(group, root_group, parents) for root_group in character_roots):
            continue
        transforms = [group.get("transform", "")]
        for class_name in group.get("class", "").split():
            transforms.extend(animation_transforms.get(class_name, ()))
        for transform in transforms:
            issue = _local_transform_issue(kind, transform)
            if issue:
                _add_once(issues, issue.code, issue.message)

    return SvgQualityResult(not issues, tuple(issues))


def safe_quality_feedback(result: SvgQualityResult) -> str:
    return " ".join(issue.message for issue in result.issues[:4])


def _tokens(element: ET.Element) -> set[str]:
    value = f"{element.get('id', '')} {element.get('class', '')}".casefold()
    return {token.casefold() for token in _TOKEN_RE.findall(value)}


def _is_character_root(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    tokens = _tokens(element)
    if "root" not in tokens or not tokens.intersection(_CHARACTER_TERMS):
        return False
    parent = parents.get(element)
    while parent is not None:
        parent_tokens = _tokens(parent)
        if parent.tag == f"{{{SVG_NS}}}g" and "root" in parent_tokens and parent_tokens.intersection(_CHARACTER_TERMS):
            return False
        parent = parents.get(parent)
    return True


def _anatomy_kind(element: ET.Element) -> str | None:
    tokens = _tokens(element)
    if tokens.intersection(_HEAD_TERMS):
        return "head"
    if tokens.intersection(_LIMB_TERMS):
        return "limb"
    if tokens.intersection(_ANATOMY_TERMS):
        return "body"
    return None


def _is_descendant(element: ET.Element, ancestor: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    current: ET.Element | None = element
    while current is not None:
        if current is ancestor:
            return True
        current = parents.get(current)
    return False


def _known_bounds(group: ET.Element) -> tuple[float, float, float, float] | None:
    boxes: list[tuple[float, float, float, float]] = []
    for element in group.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        try:
            if tag == "rect":
                x, y = float(element.get("x", "0")), float(element.get("y", "0"))
                width, height = float(element.get("width", "0")), float(element.get("height", "0"))
                boxes.append((x, y, x + width, y + height))
            elif tag == "circle":
                cx, cy, radius = float(element.get("cx", "0")), float(element.get("cy", "0")), float(element.get("r", "0"))
                boxes.append((cx - radius, cy - radius, cx + radius, cy + radius))
            elif tag == "ellipse":
                cx, cy = float(element.get("cx", "0")), float(element.get("cy", "0"))
                rx, ry = float(element.get("rx", "0")), float(element.get("ry", "0"))
                boxes.append((cx - rx, cy - ry, cx + rx, cy + ry))
            elif tag == "line":
                x1, y1 = float(element.get("x1", "0")), float(element.get("y1", "0"))
                x2, y2 = float(element.get("x2", "0")), float(element.get("y2", "0"))
                boxes.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            elif tag in {"polygon", "polyline"}:
                numbers = [float(value) for value in _NUMBER_RE.findall(element.get("points", ""))]
                if len(numbers) >= 4 and len(numbers) % 2 == 0:
                    xs, ys = numbers[::2], numbers[1::2]
                    boxes.append((min(xs), min(ys), max(xs), max(ys)))
        except ValueError:
            continue
    if not boxes:
        return None
    return min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)


def _simple_translation(transform: str) -> tuple[float, float] | None:
    dx = dy = 0.0
    for name, arguments in _TRANSFORM_RE.findall(transform):
        values = [float(value) for value in _NUMBER_RE.findall(arguments)]
        lowered = name.casefold()
        if lowered == "translate" and values:
            dx += values[0]
            dy += values[1] if len(values) > 1 else 0.0
        elif lowered == "translatex" and values:
            dx += values[0]
        elif lowered == "translatey" and values:
            dy += values[0]
        elif lowered not in {"rotate"}:
            return None
    return dx, dy


def _local_transform_issue(kind: str, transform: str) -> SvgQualityIssue | None:
    if not transform:
        return None
    translation_limit = 10.0 if kind == "head" else 20.0
    for name, arguments in _TRANSFORM_RE.findall(transform):
        values = [float(value) for value in _NUMBER_RE.findall(arguments)]
        lowered = name.casefold()
        if lowered in {"translate", "translatex", "translatey"} and values:
            x = values[0]
            y = values[1] if lowered == "translate" and len(values) > 1 else 0.0
            if math.hypot(x, y) > translation_limit + .01:
                label = "Head" if kind == "head" else "Limb"
                return SvgQualityIssue(f"excessive_{kind}_translation", f"{label} movement exceeds local character-motion limits.")
        elif lowered == "rotate" and values and abs(values[0]) > 35.01:
            return SvgQualityIssue("excessive_local_rotation", "Local body-part rotation exceeds character-motion limits.")
        elif lowered in {"scale", "scalex", "scaley"} and values:
            factors = values[:2] if len(values) > 1 else values
            if any(abs(value - 1.0) > .1501 for value in factors):
                return SvgQualityIssue("excessive_local_scale", "Local body-part scale change exceeds character-motion limits.")
        elif lowered == "matrix":
            continue
    return None


def _animation_transforms(root: ET.Element) -> dict[str, tuple[str, ...]]:
    css = "\n".join(element.text or "" for element in root.iter(f"{{{SVG_NS}}}style"))
    keyframes: dict[str, list[str]] = {}
    rules: dict[str, str] = {}
    for header, body in _css_blocks(css):
        header = header.strip()
        if header.casefold().startswith("@keyframes "):
            name = header.split(None, 1)[1].strip()
            keyframes[name] = re.findall(r"transform\s*:\s*([^;}]+)", body, flags=re.I)
        else:
            animation = re.search(r"animation(?:-name)?\s*:\s*([A-Za-z_][\w-]*)", body, flags=re.I)
            if animation:
                for selector in header.split(","):
                    match = re.fullmatch(r"\.([A-Za-z_][\w-]*)", selector.strip())
                    if match:
                        rules[match.group(1)] = animation.group(1)
    return {class_name: tuple(keyframes.get(name, ())) for class_name, name in rules.items()}


def _css_blocks(css: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    position = 0
    while position < len(css):
        while position < len(css) and css[position].isspace():
            position += 1
        opening = css.find("{", position)
        if opening < 0:
            break
        depth, closing = 1, opening + 1
        while closing < len(css) and depth:
            depth += css[closing] == "{"
            depth -= css[closing] == "}"
            closing += 1
        if depth:
            break
        blocks.append((css[position:opening], css[opening + 1:closing - 1]))
        position = closing
    return blocks


def _add_once(issues: list[SvgQualityIssue], code: str, message: str) -> None:
    if all(issue.code != code for issue in issues):
        issues.append(SvgQualityIssue(code, message))
