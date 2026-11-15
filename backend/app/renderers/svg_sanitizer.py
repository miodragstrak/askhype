from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

SVG_NS = "http://www.w3.org/2000/svg"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MAX_SVG_BYTES = 250_000
MAX_ELEMENTS = 1_200
MAX_PATH_DATA = 12_000
MAX_TEXT_LENGTH = 500
MAX_TOTAL_TEXT = 8_000
MAX_STYLE_LENGTH = 24_000
MAX_FILTERS = 12
MAX_FILTER_PRIMITIVES = 4
MAX_ANIMATION_SECONDS = 15

ALLOWED_TAGS = {
    "svg", "g", "defs", "style", "title", "desc", "path", "circle", "rect", "ellipse",
    "polygon", "polyline", "line", "text", "linearGradient", "radialGradient", "stop",
    "clipPath", "mask", "filter", "feGaussianBlur", "feDropShadow", "feComposite",
}
GLOBAL_ATTRIBUTES = {
    "id", "class", "transform", "opacity", "fill", "fill-opacity", "stroke", "stroke-opacity",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "clip-path", "mask", "filter", "style",
    "stroke-dasharray", "stroke-dashoffset", "font-family", "font-size", "font-weight",
}
TAG_ATTRIBUTES = {
    "svg": {"width", "height", "viewBox", "preserveAspectRatio", "version"},
    "path": {"d", "pathLength"}, "circle": {"cx", "cy", "r"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "ellipse": {"cx", "cy", "rx", "ry"}, "line": {"x1", "y1", "x2", "y2"},
    "polygon": {"points"}, "polyline": {"points"},
    "text": {"x", "y", "dx", "dy", "text-anchor", "font-size", "font-family", "font-weight", "letter-spacing"},
    "linearGradient": {"x1", "y1", "x2", "y2", "gradientUnits", "gradientTransform", "spreadMethod"},
    "radialGradient": {"cx", "cy", "r", "fx", "fy", "gradientUnits", "gradientTransform", "spreadMethod"},
    "stop": {"offset", "stop-color", "stop-opacity"},
    "clipPath": {"clipPathUnits"}, "mask": {"x", "y", "width", "height", "maskUnits", "maskContentUnits"},
    "filter": {"x", "y", "width", "height", "filterUnits", "color-interpolation-filters"},
    "feGaussianBlur": {"in", "stdDeviation", "result"},
    "feDropShadow": {"dx", "dy", "stdDeviation", "flood-color", "flood-opacity", "result"},
    "feComposite": {"in", "in2", "operator", "k1", "k2", "k3", "k4", "result"},
}
ALLOWED_CSS_PROPERTIES = {
    "fill", "fill-opacity", "stroke", "stroke-opacity", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stop-color", "stop-opacity",
    "stroke-dasharray", "stroke-dashoffset",
    "opacity", "transform", "transform-origin", "transform-box", "animation", "animation-name",
    "animation-duration", "animation-delay", "animation-iteration-count", "animation-timing-function",
    "animation-fill-mode", "animation-direction", "visibility", "filter",
    "clip-path", "mask", "font-family", "font-size", "font-weight", "letter-spacing", "text-anchor", "r", "rx", "ry",
    "transition",
}
SAFE_FONT_FAMILIES = {"sans-serif", "serif", "monospace", "arial", "dejavu sans", "liberation sans"}
_DURATION_RE = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)s(?![\w-])", re.I)
_SAFE_SELECTOR_RE = re.compile(r"^[#.a-zA-Z_][\w.#>+~,*\s-]*$")
_SAFE_CSS_VALUE_RE = re.compile(r"^[\w\s#.,%()+\-*/:'\"]*$")
_LOCAL_REFERENCE_RE = re.compile(r"^url\(#[A-Za-z_][\w:.-]*\)$")
_SAFE_NAMED_COLORS = {
    "black", "silver", "gray", "white", "maroon", "red", "purple", "fuchsia",
    "green", "lime", "olive", "yellow", "navy", "blue", "teal", "aqua", "transparent",
}
_COMPOSITE_OPERATORS = {"over", "in", "out", "atop", "xor", "lighter", "arithmetic"}
_FILTER_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


class SvgValidationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class SanitizedSvg:
    content: str
    element_count: int
    css_keyframes: int
    duration_seconds: float


def extract_svg_document(source: str) -> str:
    candidate = source.strip()
    lines = candidate.splitlines()
    if len(lines) >= 2 and lines[0].strip().casefold() in {"```", "```svg", "```xml"}:
        if lines[-1].strip() == "```":
            candidate = "\n".join(lines[1:-1]).strip()

    starts = list(re.finditer(r"<svg(?=[\s>])", candidate))
    closes = list(re.finditer(r"</svg\s*>", candidate))
    if not starts:
        raise SvgValidationError("missing_svg", "response does not contain an SVG document")
    if not closes:
        raise SvgValidationError("incomplete_svg", "SVG document is missing its closing </svg> tag")
    if len(starts) != 1 or len(closes) != 1 or closes[0].start() < starts[0].start():
        raise SvgValidationError("ambiguous_svg", "response does not contain exactly one usable SVG document")
    return candidate[starts[0].start():closes[0].end()]


def sanitize_svg(source: str, *, duration_seconds: float) -> SanitizedSvg:
    encoded = source.encode("utf-8")
    if len(encoded) > MAX_SVG_BYTES:
        raise SvgValidationError("document_too_large", f"maximum is {MAX_SVG_BYTES} bytes")
    lowered = source.casefold()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise SvgValidationError("xml_declaration_not_allowed", "DOCTYPE and ENTITY declarations are forbidden")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        line, column = getattr(exc, "position", (0, 0))
        reason = _safe_xml_parse_reason(str(exc))
        raise SvgValidationError(
            "invalid_xml",
            f"XML parse error at line {line} column {column}: {reason}",
        ) from exc
    if _local_name(root.tag) != "svg" or _namespace(root.tag) != SVG_NS:
        raise SvgValidationError("invalid_root", "root must be an SVG namespace element")
    if not 0 < duration_seconds <= MAX_ANIMATION_SECONDS:
        raise SvgValidationError("invalid_duration", "animation duration exceeds 15 seconds")

    elements = list(root.iter())
    if len(elements) > MAX_ELEMENTS:
        raise SvgValidationError("too_many_elements", f"maximum is {MAX_ELEMENTS} elements")
    total_text = 0
    filter_count = 0
    keyframes = 0
    for element in elements:
        namespace, tag = _namespace(element.tag), _local_name(element.tag)
        if namespace != SVG_NS:
            raise SvgValidationError("unknown_namespace", f"namespace on {tag} is not allowed")
        if tag not in ALLOWED_TAGS:
            raise SvgValidationError("disallowed_tag", tag)
        if tag == "filter":
            filter_count += 1
            if sum(1 for child in element if _local_name(child.tag).startswith("fe")) > MAX_FILTER_PRIMITIVES:
                raise SvgValidationError("filter_too_complex", "too many filter primitives")
        _validate_attributes(element, tag)
        if tag == "style":
            style = element.text or ""
            keyframes += validate_css(style)
        text_length = len(element.text or "") + len(element.tail or "")
        if tag == "text" and len(element.text or "") > MAX_TEXT_LENGTH:
            raise SvgValidationError("text_too_long", f"maximum is {MAX_TEXT_LENGTH} characters")
        total_text += text_length
    if filter_count > MAX_FILTERS:
        raise SvgValidationError("too_many_filters", f"maximum is {MAX_FILTERS}")
    if total_text > MAX_TOTAL_TEXT:
        raise SvgValidationError("text_too_large", f"maximum is {MAX_TOTAL_TEXT} characters")
    root.set("width", "1280")
    root.set("height", "720")
    root.set("viewBox", "0 0 1280 720")
    ET.register_namespace("", SVG_NS)
    return SanitizedSvg(
        content=ET.tostring(root, encoding="unicode"), element_count=len(elements),
        css_keyframes=keyframes, duration_seconds=duration_seconds,
    )


def validate_css(css: str) -> int:
    if len(css) > MAX_STYLE_LENGTH:
        raise SvgValidationError("css_too_large", f"maximum is {MAX_STYLE_LENGTH} characters")
    clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    lowered = clean.casefold()
    for token in ("url(", "@import", "@font-face", "expression(", "behavior:", "javascript:"):
        if token in lowered:
            raise SvgValidationError("unsafe_css", f"forbidden CSS token: {token}")
    blocks = _css_blocks(clean)
    keyframes = 0
    for header, body in blocks:
        header = header.strip()
        if header.casefold().startswith("@keyframes "):
            name = header.split(None, 1)[1].strip()
            if not re.fullmatch(r"[A-Za-z_][\w-]*", name):
                raise SvgValidationError("invalid_keyframes", "invalid keyframe name")
            keyframes += 1
            for selector, declarations in _css_blocks(body):
                if not all(part.strip() in {"from", "to"} or re.fullmatch(r"\d{1,3}%", part.strip()) for part in selector.split(",")):
                    raise SvgValidationError("invalid_keyframes", "invalid keyframe selector")
                _validate_declarations(declarations)
        else:
            if header.startswith("@") or not _SAFE_SELECTOR_RE.fullmatch(header):
                raise SvgValidationError("invalid_selector", "only simple SVG selectors are allowed")
            _validate_declarations(body)
    return keyframes


def _css_blocks(css: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    position = 0
    while position < len(css):
        while position < len(css) and css[position].isspace(): position += 1
        if position >= len(css): break
        opening = css.find("{", position)
        if opening < 0: raise SvgValidationError("invalid_css", "missing opening brace")
        depth, closing = 1, opening + 1
        while closing < len(css) and depth:
            if css[closing] == "{": depth += 1
            elif css[closing] == "}": depth -= 1
            closing += 1
        if depth: raise SvgValidationError("invalid_css", "unbalanced braces")
        blocks.append((css[position:opening], css[opening + 1:closing - 1]))
        position = closing
    return blocks


def _validate_declarations(body: str) -> None:
    if "{" in body or "}" in body:
        raise SvgValidationError("invalid_css", "nested rules are not allowed")
    for declaration in body.split(";"):
        if not declaration.strip(): continue
        if ":" not in declaration: raise SvgValidationError("invalid_css", "malformed declaration")
        property_name, value = (part.strip() for part in declaration.split(":", 1))
        if property_name.casefold() not in ALLOWED_CSS_PROPERTIES:
            raise SvgValidationError("disallowed_css_property", property_name[:80])
        _validate_css_value(property_name, value)


def _validate_css_value(property_name: str, value: str) -> None:
    if len(value) > 300 or not _SAFE_CSS_VALUE_RE.fullmatch(value):
        raise SvgValidationError("invalid_css_value", property_name)
    durations = [float(match) for match in _DURATION_RE.findall(value)]
    if any(duration > MAX_ANIMATION_SECONDS for duration in durations):
        raise SvgValidationError("animation_too_long", property_name)
    if property_name == "stop-color" and not _is_safe_color(value):
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name == "stop-opacity" and not _is_safe_opacity(value):
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name == "font-family" and value.strip().casefold() not in SAFE_FONT_FAMILIES:
        raise SvgValidationError("external_font", "font family is not allowlisted")
    if property_name == "font-size" and not re.fullmatch(r"(?:[1-9]\d?|1\d\d|200)(?:px)?", value, re.I):
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name == "font-weight" and not re.fullmatch(r"(?:normal|bold|[1-9]00)", value, re.I):
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name == "text-anchor" and value.casefold() not in {"start", "middle", "end"}:
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name in {"r", "rx", "ry"} and not re.fullmatch(r"(?:0|[1-9]\d{0,3})(?:\.\d+)?(?:px|%)?", value, re.I):
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name == "transition" and not re.fullmatch(
        r"(?:transform|opacity|fill|stroke|r|rx|ry)\s+\d+(?:\.\d+)?s(?:\s+(?:linear|ease|ease-in|ease-out|ease-in-out))?",
        value,
        re.I,
    ):
        raise SvgValidationError("invalid_css_value", property_name)
    if property_name == "filter" and value.casefold() != "none" and not re.fullmatch(
        r"(?:blur\((?:\d|1[0-2])(?:\.\d+)?px\)|drop-shadow\([#\w\s.,%()+-]+\))", value, re.I,
    ):
        raise SvgValidationError("unsafe_filter", "filter value is not allowlisted")


def _validate_attributes(element: ET.Element, tag: str) -> None:
    allowed = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, set())
    for raw_name, value in element.attrib.items():
        namespace, name = _namespace(raw_name), _local_name(raw_name)
        if namespace not in {"", XML_NS}:
            raise SvgValidationError("unknown_namespace", f"attribute namespace on {name} is not allowed")
        if name.casefold().startswith("on"):
            raise SvgValidationError("event_handler", name)
        if name not in allowed:
            raise SvgValidationError("disallowed_attribute", f"{tag}.{name}")
        lowered = value.strip().casefold()
        if "javascript:" in lowered or "data:" in lowered or "http:" in lowered or "https:" in lowered:
            raise SvgValidationError("external_reference", f"{tag}.{name}")
        if "url(" in lowered:
            if name not in {"fill", "stroke", "filter", "clip-path", "mask"} or not _LOCAL_REFERENCE_RE.fullmatch(value.strip()):
                raise SvgValidationError("external_reference", f"{tag}.{name}")
        if name == "style": _validate_declarations(value)
        if name == "d" and len(value) > MAX_PATH_DATA:
            raise SvgValidationError("path_too_long", f"maximum is {MAX_PATH_DATA} characters")
        if name == "points" and len(value) > MAX_PATH_DATA:
            raise SvgValidationError("points_too_long", f"maximum is {MAX_PATH_DATA} characters")
        if name == "font-family" and value.strip().casefold() not in SAFE_FONT_FAMILIES:
            raise SvgValidationError("external_font", "font family is not allowlisted")
        if name == "font-size" and not re.fullmatch(r"(?:[1-9]\d?|1\d\d|200)(?:px)?", value, re.I):
            raise SvgValidationError("invalid_attribute", f"{tag}.{name}")
        if name == "font-weight" and not re.fullmatch(r"(?:normal|bold|[1-9]00)", value, re.I):
            raise SvgValidationError("invalid_attribute", f"{tag}.{name}")
        if tag == "stop" and name == "stop-color" and not _is_safe_color(value):
            raise SvgValidationError("invalid_attribute", f"{tag}.{name}")
        if tag == "stop" and name == "stop-opacity" and not _is_safe_opacity(value):
            raise SvgValidationError("invalid_attribute", f"{tag}.{name}")
        if tag in {"feGaussianBlur", "feDropShadow"} and name == "stdDeviation":
            try: blur = max(float(part) for part in value.replace(",", " ").split())
            except ValueError as exc: raise SvgValidationError("invalid_filter", "invalid blur") from exc
            if blur > 12: raise SvgValidationError("unsafe_filter", "blur exceeds 12")
        if tag == "feComposite" and name == "operator" and value not in _COMPOSITE_OPERATORS:
            raise SvgValidationError("invalid_filter", "feComposite operator is not allowlisted")
        if tag == "feComposite" and name in {"k1", "k2", "k3", "k4"}:
            if not _is_bounded_filter_number(value):
                raise SvgValidationError("invalid_filter", f"feComposite {name} must be between -10 and 10")


def _namespace(name: str) -> str:
    return name[1:].split("}", 1)[0] if name.startswith("{") else ""


def _local_name(name: str) -> str:
    return name.split("}", 1)[-1]


def _is_safe_color(value: str) -> bool:
    candidate = value.strip().casefold()
    if re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{1}|[0-9a-f]{3}(?:[0-9a-f]{2})?)?", candidate):
        return True
    if candidate in _SAFE_NAMED_COLORS:
        return True
    function = re.fullmatch(r"(rgb|rgba)\(([^()]*)\)", candidate)
    if not function:
        return False
    parts = [part.strip() for part in function.group(2).split(",")]
    expected = 4 if function.group(1) == "rgba" else 3
    if len(parts) != expected:
        return False
    try:
        channels_valid = all(
            0 <= float(part[:-1]) <= 100 if part.endswith("%") else part.isdigit() and 0 <= int(part) <= 255
            for part in parts[:3]
        )
        alpha_valid = expected == 3 or _is_safe_opacity(parts[3])
    except ValueError:
        return False
    return channels_valid and alpha_valid


def _is_safe_opacity(value: str) -> bool:
    candidate = value.strip()
    if not re.fullmatch(r"(?:0(?:\.\d+)?|1(?:\.0+)?|\.\d+)", candidate):
        return False
    return 0 <= float(candidate) <= 1


def _is_bounded_filter_number(value: str) -> bool:
    candidate = value.strip()
    if not _FILTER_NUMBER_RE.fullmatch(candidate):
        return False
    number = float(candidate)
    return -10 <= number <= 10


def _safe_xml_parse_reason(parser_message: str) -> str:
    lowered = parser_message.casefold()
    categories = (
        ("mismatched tag", "mismatched tag"),
        ("no element found", "no element found"),
        ("unclosed token", "unclosed token"),
        ("invalid token", "not well-formed (invalid token)"),
        ("junk after document element", "junk after document element"),
        ("duplicate attribute", "duplicate attribute"),
        ("undefined entity", "undefined entity"),
        ("xml or text declaration not at start", "XML declaration is not at the start"),
        ("encoding declaration", "invalid encoding declaration"),
        ("recursive entity reference", "recursive entity reference"),
        ("amplification", "input amplification limit exceeded"),
    )
    return next((safe for marker, safe in categories if marker in lowered), "XML syntax error")
