"""Deterministic executive layouts. Coordinates are in inches."""

from decimal import Decimal, InvalidOperation
from io import BytesIO
import math
import re
from textwrap import wrap
from typing import Protocol

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.schemas.presentations import BulletsSlide, ConclusionSlide, KeyMetricsSlide, TableSlide
from app.services.presentation_diagnostics import PresentationDiagnostics, PresentationRuleError
from app.services.presentation_illustrations import Illustration, illustration_slot_rejection

WIDTH, HEIGHT = 13.333, 7.5
LEFT, CONTENT = .72, 11.89
PAPER, NAVY, TEAL, GOLD, MUTED, WHITE = (
    RGBColor.from_string(value) for value in ("F8F7F3", "142638", "176B66", "DFC17B", "4B5D69", "FFFFFF")
)
FONT = "Liberation Sans"
_STATUS_LABELS = {
    "en": {"proposal": "PROPOSAL", "assumption": "ASSUMPTION", "illustrative": "ILLUSTRATIVE"},
    "sr": {"proposal": "PREDLOG", "assumption": "PRETPOSTAVKA", "illustrative": "ILUSTRATIVNO"},
    "cyrl": {"proposal": "ПРЕДЛОГ", "assumption": "ПРЕТПОСТАВКА", "illustrative": "ИЛУСТРАТИВНО"},
}

_LAYOUTS = {
    "title": {"cover"}, "section": {"findings"},
    "bullets": {"summary", "findings", "pillars", "comparison", "problem_solution", "process", "roadmap",
                "recommendations", "business_model", "timeline", "worked_example"},
    "conclusion": {"closing", "recommendations"}, "key_metrics": {"kpi"}, "table": {"table", "chart", "worked_example"},
}
_DEFAULT = {"title": "cover", "section": "findings", "bullets": "findings",
            "conclusion": "closing", "key_metrics": "kpi", "table": "table"}
_NUMERIC_TOKEN = re.compile(r"(?<!\w)[+−-]?\d+(?:[.,]\d+)?(?:[ \t]*%)?(?!\w)")


def _number(text):
    text = text.strip().replace("−", "-")
    if not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?\s*%?", text):
        raise PresentationRuleError("numeric_format", "Quantitative values must contain a finite number.")
    try:
        value = float(Decimal(text.rstrip("%").strip().replace(",", ".")))
    except (InvalidOperation, OverflowError) as exc:
        raise PresentationRuleError("numeric_conversion", "Invalid quantitative value.") from exc
    if not math.isfinite(value) or abs(value) > 1e15:
        raise PresentationRuleError("numeric_bounds", "Quantitative value exceeds supported bounds.")
    return value


def verify_quantitative_evidence(plan, document_text, diagnostics=None):
    """Require literal numeric tokens in the supplied extraction for charts and KPIs."""
    def normalize(token):
        return re.sub(r"\s+", "", token).replace("−", "-").replace(",", ".")

    supplied = {normalize(token) for token in _NUMERIC_TOKEN.findall(document_text)}
    for index, slide in enumerate(plan.slides, 1):
        if diagnostics:
            diagnostics.slide(index, slide.layout or slide.type)
        if isinstance(slide, KeyMetricsSlide):
            if _hypothetical_targets(slide):
                continue
            values = [metric.value for metric in slide.metrics]
        elif isinstance(slide, TableSlide) and slide.layout == "chart" and slide.evidence_ids:
            if any(len(row) != len(slide.headers) for row in slide.rows):
                raise PresentationRuleError("table_dimensions", "Chart rows must match the header width.")
            values = [cell for row in slide.rows for cell in row[1:]]
        else:
            continue
        for value in values:
            _number(value)
            if normalize(value) not in supplied:
                raise PresentationRuleError("missing_numeric_evidence", "Quantitative value is absent from supplied evidence.")


def _wrapped(value, width, size, *, factor=.61):
    capacity = max(1, int(width * 72 / (size * factor)))
    return [line for part in value.strip().splitlines() for line in wrap(part, capacity)]


def _fits(value, width, height, size):
    return len(_wrapped(value, width, size)) <= int(height * 72 / (size * 1.22))


class Canvas:
    def __init__(self, slide):
        self.slide = slide
        self.regions = []

    def region(self, x, y, w, h):
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > WIDTH + .001 or y + h > HEIGHT + .001:
            raise PresentationRuleError("element_bounds", "Slide element is outside the canvas.")
        if any(x < a + c - .001 and x + w > a + .001 and y < b + d - .001 and y + h > b + .001
               for a, b, c, d in self.regions):
            raise PresentationRuleError("element_overlap", "Slide content regions overlap.")
        self.regions.append((x, y, w, h))

    def panel(self, x, y, w, h, color=WHITE, kind=MSO_SHAPE.RECTANGLE):
        shape = self.slide.shapes.add_shape(kind, *map(Inches, (x, y, w, h)))
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def text(self, value, x, y, w, h, size, color=NAVY, *, bold=False, minimum=None):
        value = value.strip()
        if not value:
            return
        if size < 12:
            raise PresentationRuleError("minimum_font_size", "Visible text must be at least 12 points.")
        for candidate in range(size, (minimum or size) - 1, -1):
            if _fits(value, w, h, candidate):
                size = candidate
                break
        else:
            raise PresentationRuleError("text_fit", "Slide text does not fit its layout at a readable size.")
        lines = _wrapped(value, w, size)
        self.region(x, y, w, h)
        frame = self.slide.shapes.add_textbox(*map(Inches, (x, y, w, h))).text_frame
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        frame.word_wrap = True
        paragraph = frame.paragraphs[0]
        paragraph.text = "\v".join(lines)
        paragraph.line_spacing = Pt(size * 1.19)
        _font(paragraph.font, size, color, bold)


def _font(font, size, color=NAVY, bold=False):
    font.name, font.size, font.bold = FONT, Pt(size), bold
    font.color.rgb = color


def _hypothetical_targets(item):
    return (isinstance(item, KeyMetricsSlide) and item.claim_status in {"proposal", "illustrative"}
            and not item.evidence_ids)


def _table_dimensions(item):
    if any(len(row) != len(item.headers) for row in item.rows):
        raise PresentationRuleError("table_dimensions", "Svi redovi tabele moraju imati isti broj kolona kao zaglavlje.")


def _chart_data(item):
    _table_dimensions(item)
    if len(item.headers) < 2 or len(item.rows) < 2:
        raise PresentationRuleError("chart_dimensions", "Charts require at least two categories and one series.")
    if any(not row[0].strip() or len(row[0]) > 24 for row in item.rows):
        raise PresentationRuleError("chart_category_label", "Charts require readable category labels.")
    units = {cell.strip().endswith("%") for row in item.rows for cell in row[1:]}
    if len(units) != 1 or any(not label.strip() or len(label) > 32 for label in item.headers[1:]):
        raise PresentationRuleError("chart_series_units", "Chart series need readable labels and consistent units.")
    values = [[_number(row[column]) for row in item.rows] for column in range(1, len(item.headers))]
    if len(item.headers) > 2:
        declared = [re.search(r"\(([^()]+)\)\s*$", header) for header in item.headers[1:]]
        if (any(declared) and (not all(declared) or len({match[1].strip().casefold() for match in declared if match}) != 1)
                or not any(declared) and units == {False}):
            raise PresentationRuleError("chart_series_units", "Numeric series require the same explicit unit in their headers.")
    return units, values


def _table(canvas, item, chart):
    _table_dimensions(item)
    box = (LEFT, 1.88, CONTENT, 4.53 if chart else min(4.53, .72 * (len(item.rows) + 1)))
    if chart:
        canvas.region(*box)
        units, series_values = _chart_data(item)
        data = CategoryChartData()
        data.categories = [row[0] for row in item.rows]
        for label, values in zip(item.headers[1:], series_values):
            data.add_series(label, values)
        chart_object = canvas.slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, *map(Inches, box), data).chart
        chart_object.font.name = FONT
        chart_object.font.size = Pt(14)
        for series, color in zip(chart_object.series, (TEAL, NAVY, GOLD, MUTED)):
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = color
        if len(item.headers) == 2:
            series = chart_object.series[0]
            values = list(series.values)
            peak = max(values)
            if values.count(peak) == 1 and item.takeaway:
                point = series.points[values.index(peak)]
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = NAVY
        chart_object.has_legend = len(item.headers) > 2
        chart_object.value_axis.has_major_gridlines = False
        plot = chart_object.plots[0]
        plot.has_data_labels = True
        plot.data_labels.position = XL_DATA_LABEL_POSITION.OUTSIDE_END
        _font(plot.data_labels.font, 14, NAVY, True)
        if chart_object.has_legend:
            chart_object.legend.position = XL_LEGEND_POSITION.BOTTOM
        if True in units:
            chart_object.value_axis.tick_labels.number_format = '0"%"'
            plot.data_labels.number_format = '0.##"%"'
        if len(item.headers) == 2:
            chart_object.has_title = True
            chart_object.chart_title.text_frame.text = item.headers[1]
        return
    rows = [item.headers, *item.rows]
    for size in (14, 13, 12):
        line_spacing = size * 1.22
        wrapped = [[_wrapped(text, CONTENT / len(item.headers) - .24, size, factor=.66)
                    for text in row] for row in rows]
        heights = [max(.37, .16 + max(map(len, row)) * line_spacing / 72) for row in wrapped]
        if sum(heights) <= 4.53:
            break
    else:
        raise PresentationRuleError("table_text_fit", "Table content cannot fit at a readable size.")
    if sum(heights) > box[3]:
        box = (*box[:3], sum(heights))
    canvas.region(*box)
    table = canvas.slide.shapes.add_table(len(rows), len(item.headers), *map(Inches, box)).table
    for row, height in zip(table.rows, heights):
        row.height = Inches(height + (box[3] - sum(heights)) / len(rows))
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            cell = table.cell(i, j)
            cell.text = "\v".join(wrapped[i][j])
            cell.margin_top = cell.margin_bottom = Inches(.06)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (WHITE if i % 2 else PAPER)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.line_spacing = Pt(line_spacing)
                _font(paragraph.font, size, WHITE if i == 0 else NAVY, i == 0)
                if i > 0 and _NUMERIC_TOKEN.fullmatch(text.strip()):
                    paragraph.alignment = PP_ALIGN.RIGHT


class VisualAssets(Protocol):
    def draw(self, canvas: Canvas, concept: str, x: float, y: float) -> None: ...


class NativeVisualAssets:
    """Small editable symbols. The renderer owns their placement and scale."""

    def draw(self, canvas, concept, x, y):
        shapes = {
            "business": MSO_SHAPE.HEXAGON, "technology": MSO_SHAPE.DIAMOND,
            "education": MSO_SHAPE.FOLDED_CORNER, "media": MSO_SHAPE.ISOSCELES_TRIANGLE,
            "finance": MSO_SHAPE.PARALLELOGRAM, "process": MSO_SHAPE.CHEVRON,
            "strategy": MSO_SHAPE.RIGHT_ARROW,
        }
        symbol = canvas.panel(x, y, .34, .34, TEAL, shapes[concept])
        if concept == "media":
            symbol.rotation = 90


def _line(canvas, x, y, end_x, end_y, color=TEAL):
    line = canvas.slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, *map(Inches, (x, y, end_x, end_y)))
    line.line.color.rgb = color
    line.line.width = Pt(1.4)


def _heading(canvas, value, x, y, width, height, size=20, color=TEAL):
    # Keep the complete heading and use the allotted space before reducing type.
    minimum = min(size, 18 if size >= 22 else 14)
    for candidate in range(size, minimum - 1, -1):
        capacity = max(1, int(width * 72 / (candidate * .61)))
        lines = sum(len(wrap(part, capacity)) for part in value.strip().splitlines())
        if lines <= int(height * 72 / (candidate * 1.22)):
            size = candidate
            break
    canvas.text(value, x, y, width, height, size, color, bold=True)


def _bullet_items(bullets, layout):
    items = []
    for i, value in enumerate(bullets, 1):
        label, separator, body = value.partition(":")
        if layout != "findings" and separator and 0 < len(label) <= 34 and body.strip():
            items.append((label.strip(), body.strip()))
        else:
            items.append((f"{i:02d}", value))
    return items


def _compose(canvas, items, layout, assets):
    count = len(items)
    if layout == "kpi":
        if count == 1:
            value, label = items[0]
            assets.draw(canvas, "finance", LEFT, 2.12)
            _heading(canvas, value, LEFT, 2.73, 5.55, 2.2, 64)
            _line(canvas, 6.55, 2.48, 6.55, 5.48)
            canvas.text(label, 7.0, 3.1, 5.1, 1.65, 25)
            return
        width = (CONTENT - .32 * (count - 1)) / count
        for i, (value, label) in enumerate(items):
            x = LEFT + i * (width + .32)
            canvas.panel(x, 2.42, width, .055, TEAL)
            _heading(canvas, value, x, 2.78, width, 2.05, 40)
            canvas.text(label, x, 4.91, width, 1.24, 17)
        return

    if layout in {"comparison", "problem_solution"}:
        _line(canvas, 6.54, 2.28, 6.54, 5.85)
        for i, (label, body) in enumerate(items):
            x = LEFT if i == 0 else 7.03
            width = 5.43
            canvas.panel(x, 2.36, .73, .065, GOLD if i == 0 and layout == "problem_solution" else TEAL)
            _heading(canvas, label, x, 2.65, width, 1.13, 23)
            canvas.text(body, x, 3.93, width, 2.08, 20)
        if layout == "problem_solution":
            canvas.panel(6.32, 3.28, .44, .29, TEAL, MSO_SHAPE.RIGHT_ARROW)
        return

    if layout in {"process", "timeline", "roadmap", "business_model"} and 2 <= count <= 6:
        if layout == "timeline":
            step = 4.18 / count
            _line(canvas, 1.12, 2.02, 1.12, 2.02 + (count - 1) * step)
            for i, (label, body) in enumerate(items):
                y = 1.90 + i * step
                canvas.panel(.99, y, .26, .26, TEAL, MSO_SHAPE.OVAL)
                _heading(canvas, label, 1.55, y, 2.88, step - .08, 16)
                canvas.text(body, 4.74, y, 7.65, step - .08, 16, minimum=14)
            return
        step = CONTENT / count
        center = [LEFT + (i + .5) * step for i in range(count)]
        _line(canvas, center[0], 3.64, center[-1], 3.64)
        for i, (label, body) in enumerate(items):
            x = LEFT + i * step + .10
            top = layout == "roadmap" and i % 2 == 0
            canvas.panel(center[i] - .15, 3.49, .30, .30, GOLD if top else TEAL, MSO_SHAPE.OVAL)
            if layout in {"process", "business_model"} and i < count - 1:
                canvas.panel(center[i] + step / 2 - .15, 3.49, .30, .30, TEAL, MSO_SHAPE.CHEVRON)
            label_y, body_y = (1.88, 2.55) if top else (4.0, 4.76)
            _heading(canvas, label, x, label_y, step - .20, .65, 15)
            canvas.text(body, x, body_y, step - .20, .85 if top else 1.56, 16, minimum=14)
        return

    if layout == "pillars" and count <= 3:
        width = (CONTENT - .62 * (count - 1)) / count
        for i, (label, body) in enumerate(items):
            x = LEFT + i * (width + .62)
            assets.draw(canvas, ("business", "media", "technology")[i], x, 2.34)
            _heading(canvas, label, x, 2.95, width, .93, 22)
            canvas.text(body, x, 4.02, width, 1.95, 20)
        return

    if layout == "recommendations" and count <= 4:
        assets.draw(canvas, "strategy", LEFT, 1.98)
        step = 4.08 / count
        for i, (label, body) in enumerate(items):
            y = 2.40 + i * step
            canvas.panel(LEFT, y + .05, .09, min(.48, step - .13), GOLD if i == 0 else TEAL)
            _heading(canvas, label, 1.03, y, 3.22, min(.81, step - .10), 20, NAVY)
            canvas.text(body, 4.64, y, 7.80, step - .13, 19, minimum=14)
            if i < count - 1:
                _line(canvas, LEFT, y + step - .09, 12.43, y + step - .09, RGBColor.from_string("BCCBC6"))
        return

    if layout in {"summary", "worked_example"} and count <= 4:
        label, body = items[0]
        assets.draw(canvas, {"summary": "business", "worked_example": "education"}[layout], LEFT, 2.05)
        _heading(canvas, label, LEFT, 2.62, 5.30, .92, 23)
        canvas.text(body, LEFT, 3.70, 5.30, 2.48, 23, minimum=15)
        if count > 1:
            _line(canvas, 6.48, 2.05, 6.48, 6.15)
        y = 2.15
        for label, body in items[1:]:
            _heading(canvas, label, 6.91, y, 5.56, .56, 16)
            canvas.text(body, 6.91, y + .59, 5.56, .76, 17, minimum=14)
            y += 1.38
        return

    # Dense material reads as an editorial list. No fixed-height card backgrounds.
    step = min(1.12, 4.52 / count)
    for i, (label, body) in enumerate(items):
        y = 1.91 + i * step
        _heading(canvas, f"{i + 1:02d}", LEFT, y, .46, .34, 15)
        text = body if label == f"{i + 1:02d}" else f"{label}: {body}"
        canvas.text(text, LEFT + .68, y, CONTENT - .68, step - .08, 17, minimum=14)

def render_executive(plan, evidence_ids=frozenset(), *, assets: VisualAssets | None = None,
                     diagnostics: PresentationDiagnostics | None = None,
                     illustrations: dict[int, Illustration] | None = None):
    assets = assets or NativeVisualAssets()
    trace = diagnostics or PresentationDiagnostics()
    trace.slide()
    with trace.measure("initialize_deck", "rendering"):
        deck = Presentation()
        deck.slide_width, deck.slide_height = Inches(WIDTH), Inches(HEIGHT)
    recent = []
    for index, item in enumerate(plan.slides, 1):
        trace.slide(index, item.layout or item.type)
        with trace.measure("select_layout", "validation"):
            layout, bullets = _select_layout(item, evidence_ids, recent, trace)
        trace.resolved_layouts[index] = layout
        with trace.measure("render_slide", "rendering"):
            _render_slide(deck, plan, item, index, layout, bullets, assets, (illustrations or {}).get(index))
    trace.slide()
    with trace.measure("serialize_pptx", "rendering"):
        output = BytesIO()
        deck.save(output)
        content = output.getvalue()
    with trace.measure("validate_pptx_integrity", "validation"):
        if len(Presentation(BytesIO(content)).slides) != len(plan.slides):
            raise PresentationRuleError("pptx_slide_count", "Generated presentation failed integrity validation.")
    return content


def _select_layout(item, evidence_ids, recent, trace):
    if not item.title.strip() or set(item.evidence_ids) - evidence_ids:
        raise PresentationRuleError("title_or_evidence_reference", "Invalid title or evidence reference.")
    if item.claim_status == "evidence" and not item.evidence_ids:
        raise PresentationRuleError("missing_evidence_reference", "Evidence-backed slides need a source reference.")
    layout = item.layout if item.layout in _LAYOUTS[item.type] else _DEFAULT[item.type]
    rule, reason = "layout_slide_type", "Requested layout is incompatible with the typed slide."
    trace.selected_layout = layout
    if layout == "chart" and not item.evidence_ids:
        raise PresentationRuleError("missing_quantitative_reference", "Factual charts require a source reference.")
    if _hypothetical_targets(item):
        layout, rule, reason = "table", "hypothetical_targets", "Show explicitly hypothetical targets as a labeled table."
    if isinstance(item, TableSlide):
        _table_dimensions(item)
    if layout == "worked_example" and isinstance(item, TableSlide) and item.claim_status != "illustrative":
        raise PresentationRuleError("illustrative_chart_label", "Teaching charts must be clearly labeled illustrative.")
    if layout == "worked_example" and isinstance(item, TableSlide):
        try:
            _chart_data(item)
        except PresentationRuleError as exc:
            if exc.rule not in {"numeric_format", "chart_dimensions", "chart_category_label", "chart_series_units"}:
                raise
            layout, rule, reason = "table", exc.rule, str(exc)
    bullets = [value for value in getattr(item, "bullets", []) if value.strip()]
    if layout in {"comparison", "problem_solution"} and len(bullets) != 2:
        layout = "findings"
        rule, reason = "paired_content", "The comparison requires exactly two entries."
    if layout in {"process", "roadmap", "timeline", "business_model"} and len(bullets) < 2:
        raise PresentationRuleError("diagram_steps", "An ordered diagram requires at least two steps.")
    if layout in {"roadmap", "process", "business_model"}:
        width = CONTENT / len(bullets) - .20
        for i, (label, body) in enumerate(_bullet_items(bullets, layout)):
            height = .85 if layout == "roadmap" and i % 2 == 0 else 1.56
            if not _fits(label, width, .65, 14) or not _fits(body, width, height, 14):
                layout, rule, reason = "timeline", "text_fit", "Use wider milestone rows to preserve complete text."
                break
    if layout in {"summary", "recommendations", "worked_example"} and len(bullets) > 4:
        layout = "findings"
        rule, reason = "content_density", "Too many entries for the requested layout."
    if layout == "pillars" and len(bullets) > 3:
        layout = "findings"
        rule, reason = "content_density", "Too many entries for the pillars layout."
    if len(recent) >= 2 and recent[-2:] == [layout, layout] and layout in {"findings", "pillars"} and isinstance(item, BulletsSlide):
        alternative = "pillars" if layout == "findings" and len(bullets) <= 3 else "findings"
        if alternative != layout:
            layout = alternative
            rule, reason = "layout_repetition", "Avoid consecutive identical compositions."
    trace.selected_layout = layout
    if layout != (item.layout or _DEFAULT[item.type]):
        trace.fallback(layout, rule, reason)
    recent.append(layout)
    return layout, bullets


def _picture(canvas, illustration, x, y, w, h, *, overlay=False):
    if not overlay:
        canvas.region(x, y, w, h)
    shape = canvas.slide.shapes.add_picture(BytesIO(illustration.jpeg), *map(Inches, (x, y, w, h)))
    image_ratio = illustration.width / illustration.height
    slot_ratio = w / h
    if image_ratio > slot_ratio:
        shape.crop_left = shape.crop_right = (1 - slot_ratio / image_ratio) / 2
    else:
        shape.crop_top = shape.crop_bottom = (1 - image_ratio / slot_ratio) / 2


def _render_slide(deck, plan, item, index, layout, bullets, assets, illustration=None):
    dark = layout in {"cover", "closing"}
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.name = layout
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = NAVY if dark else PAPER
    canvas = Canvas(slide)
    use_picture = illustration and illustration_slot_rejection(item, layout, illustration.crop_region, index) is None
    cover_picture = use_picture and layout == "cover"
    split_picture = use_picture and illustration.crop_region == "split_right"
    if cover_picture:
        if illustration.crop_region == "full_bleed":
            _picture(canvas, illustration, 0, 0, WIDTH, HEIGHT, overlay=True)
            canvas.panel(0, 0, 7.8, HEIGHT, NAVY)
        else:
            _picture(canvas, illustration, 7.8, 0, WIDTH - 7.8, HEIGHT, overlay=True)
    if split_picture:
        _picture(canvas, illustration, 7.18, 1.94, 5.43, 4.4)
    canvas.text(layout.replace("_", " ").upper() if plan.language.lower().startswith("en") else f"{index:02d}",
                LEFT, .34, 3.7 if cover_picture else 6, .26, 13, GOLD if dark else TEAL, bold=True)
    locale = "cyrl" if re.search(r"[А-Яа-яЋћЂђ]", item.title) and plan.language.lower().startswith("sr") else (
        "sr" if plan.language.lower().startswith("sr") else "en"
    )
    canvas.text(_STATUS_LABELS[locale].get(item.claim_status, ""), 4.8 if cover_picture else 9.25, .34,
                2.8 if cover_picture else 3.36, .26, 13,
                GOLD if dark else TEAL, bold=True)
    if layout == "cover":
        if not cover_picture:
            canvas.panel(9.72, 0, 3.61, HEIGHT, RGBColor.from_string("1D394A"))
            canvas.panel(10.35, 1.26, 2.03, 2.03, TEAL, MSO_SHAPE.OVAL)
            canvas.panel(11.23, 2.56, 1.40, 1.40, GOLD, MSO_SHAPE.OVAL)
            canvas.panel(10.35, 4.35, 2.03, .06, GOLD)
        _heading(canvas, item.title, LEFT, 1.37, 6.55 if cover_picture else 8.55, 3.12, 42, WHITE)
    else:
        _heading(canvas, item.title, LEFT, .69, CONTENT, 1.18, 28, WHITE if dark else NAVY)
    if isinstance(item, TableSlide):
        if not all(header.strip() for header in item.headers) or any(not any(cell.strip() for cell in row) for row in item.rows):
            raise PresentationRuleError("empty_table_content", "Tables require headings and non-empty rows.")
        if layout == "worked_example" and not item.takeaway.strip():
            raise PresentationRuleError("worked_example_explanation", "A worked chart needs an explanation.")
        _table(canvas, item, layout in {"chart", "worked_example"})
    elif isinstance(item, KeyMetricsSlide):
        if _hypothetical_targets(item):
            if any(not metric.label.strip() or not metric.value.strip() for metric in item.metrics):
                raise PresentationRuleError("metric_label", "Targets require labels and values.")
            headers = {"en": ["Indicator", "Target"], "sr": ["Pokazatelj", "Cilj"],
                       "cyrl": ["Показатељ", "Циљ"]}[locale]
            targets = TableSlide(type="table", title=item.title, headers=headers,
                                 rows=[[metric.label, metric.value] for metric in item.metrics])
            _table(canvas, targets, False)
        elif not item.evidence_ids:
            raise PresentationRuleError("missing_quantitative_reference", "Quantitative slides require a source reference.")
        else:
            for metric in item.metrics:
                _number(metric.value)
                if not metric.label.strip():
                    raise PresentationRuleError("metric_label", "Metrics require labels.")
            _compose(canvas, [(metric.value, metric.label) for metric in item.metrics], "kpi", assets)
    elif isinstance(item, (BulletsSlide, ConclusionSlide)):
        if not bullets:
            raise PresentationRuleError("empty_slide_content", "Content slides cannot be empty.")
        if layout == "closing":
            canvas.panel(LEFT, 2.05, .74, .08, GOLD)
            canvas.panel(11.24, 2.12, 1.36, 1.36, TEAL, MSO_SHAPE.RIGHT_ARROW)
            canvas.text(bullets[0], LEFT, 2.48, 9.72, 2.02, 32, WHITE, bold=True, minimum=20)
            if len(bullets) > 1:
                canvas.text("\n".join(f"• {value}" for value in bullets[1:]), LEFT, 4.67, 11.62, 1.76, 18, WHITE, minimum=14)
        elif split_picture:
            for i, text in enumerate(bullets):
                y = 2.05 + i * 1.30
                canvas.text(f"{i + 1:02d}", LEFT, y, .48, .38, 16, TEAL, bold=True)
                canvas.text(text, LEFT + .65, y, 5.38, 1.15, 17)
        else:
            _compose(canvas, _bullet_items(bullets, layout), layout, assets)
    else:
        subtitle = getattr(item, "subtitle", None) or item.takeaway
        if item.type == "section" and not subtitle.strip():
            raise PresentationRuleError("section_takeaway", "Section slides require a substantive takeaway.")
        canvas.text(subtitle, LEFT, 4.72 if dark else 2.25, 6.55 if cover_picture else 8.55 if dark else 10.5, 1.44, 23,
                    GOLD if dark else MUTED, minimum=14)
    if item.takeaway and item.takeaway != getattr(item, "subtitle", None) and layout != "cover":
        canvas.text(item.takeaway, LEFT, 6.56, CONTENT, .47, 15, GOLD if dark else TEAL, minimum=12)
    canvas.text(f"{index:02d} / {len(plan.slides):02d}", LEFT if cover_picture else 11.45, 7.11, 1.15,
                .23, 12, WHITE if dark else MUTED)
    evidence = ", ".join(item.evidence_ids)
    notes = [item.objective, item.takeaway, item.speaker_notes, item.claim_status, evidence,
             "Illustration is conceptual and is not source evidence." if cover_picture or split_picture else ""]
    slide.notes_slide.notes_text_frame.text = "\n\n".join(value for value in dict.fromkeys(notes) if value)
    for shape in slide.shapes:
        if (min(shape.left, shape.top) < 0 or shape.left + shape.width > deck.slide_width
                or shape.top + shape.height > deck.slide_height):
            raise PresentationRuleError("rendered_shape_bounds", "Rendered shape is outside the canvas.")
