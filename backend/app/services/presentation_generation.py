import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

from app.core.config import settings
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockAIProvider
from app.schemas.documents import ExtractedDocument
from app.schemas.presentations import (
    BulletsSlide, ConclusionSlide, KeyMetricsSlide, PresentationPlan,
    SectionSlide, TableSlide, TitleSlide,
)
from app.services.chat_service import UnsupportedAIProviderError

MARINE = RGBColor(0x0B, 0x12, 0x20)
WHITE = RGBColor(0xF8, 0xFA, 0xFC)
BLUE = RGBColor(0x25, 0x3C, 0x91)
YELLOW = RGBColor(0xFC, 0xD3, 0x4D)
MUTED = RGBColor(0xA7, 0xB2, 0xC5)
MAX_BULLET_CHARS = 180
MAX_TABLE_CELL_CHARS = 80


class PresentationGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class PresentationResult:
    content: bytes
    filename: str
    slide_count: int
    summary: str
    warnings: tuple[str, ...]


def requested_slide_count(prompt: str) -> tuple[int, tuple[str, ...]]:
    match = re.search(r"\b(\d{1,3})\s*(?:slajd|slide)", prompt.casefold())
    requested = int(match.group(1)) if match else 6
    if requested < 3:
        return 3, ("Broj slajdova je povećan na minimalna 3.",)
    if requested > 12:
        return 12, ("Broj slajdova je ograničen na maksimalnih 12.",)
    return requested, ()


class PresentationGenerationService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or self._provider_from_settings()

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    async def generate(self, prompt: str, document: ExtractedDocument | None) -> PresentationResult:
        count, warnings = requested_slide_count(prompt)
        plan = await self.provider.generate_presentation_plan(prompt, count, document)
        if len(plan.slides) != count:
            raise PresentationGenerationError(f"Plan mora imati tačno {count} slajdova.")
        content = render_presentation(plan)
        return PresentationResult(
            content=content,
            filename=_safe_filename(plan.title),
            slide_count=count,
            summary=f"Prezentacija „{plan.title}” je napravljena sa {count} slajdova.",
            warnings=warnings,
        )

    @staticmethod
    def _provider_from_settings() -> AIProvider:
        if settings.ai_provider == "mock": return MockAIProvider()
        if settings.ai_provider == "gemini": return GeminiProvider()
        raise UnsupportedAIProviderError(f"Unsupported AI_PROVIDER value: {settings.ai_provider}")


def render_presentation(plan: PresentationPlan) -> bytes:
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    for item in plan.slides:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        _background(slide, MARINE)
        _accent(slide)
        if isinstance(item, TitleSlide): _render_title(slide, item.title, item.subtitle)
        elif isinstance(item, SectionSlide): _render_section(slide, item.title, item.subtitle)
        elif isinstance(item, (BulletsSlide, ConclusionSlide)): _render_bullets(slide, item.title, item.bullets)
        elif isinstance(item, KeyMetricsSlide): _render_metrics(slide, item)
        elif isinstance(item, TableSlide): _render_table(slide, item)
    output = io.BytesIO()
    presentation.save(output)
    return output.getvalue()


def _background(slide, color: RGBColor) -> None:
    fill = slide.background.fill; fill.solid(); fill.fore_color.rgb = color


def _accent(slide) -> None:
    shape = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.16), Inches(7.5))
    shape.fill.solid(); shape.fill.fore_color.rgb = YELLOW; shape.line.fill.background()


def _textbox(slide, text: str, left, top, width, height, size: int, color=WHITE, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame; frame.clear(); frame.word_wrap = True; frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]; paragraph.text = text; paragraph.alignment = align
    paragraph.font.name = "Aptos"; paragraph.font.size = Pt(size); paragraph.font.bold = bold; paragraph.font.color.rgb = color
    return box


def _render_title(slide, title: str, subtitle: str | None) -> None:
    _textbox(slide, title, Inches(0.9), Inches(1.7), Inches(11.5), Inches(1.5), 34, WHITE, True)
    if subtitle: _textbox(slide, subtitle, Inches(0.95), Inches(3.3), Inches(10.8), Inches(0.9), 18, MUTED)


def _render_section(slide, title: str, subtitle: str | None) -> None:
    _textbox(slide, title, Inches(1), Inches(2.1), Inches(11.2), Inches(1.2), 30, YELLOW, True, PP_ALIGN.CENTER)
    if subtitle: _textbox(slide, subtitle, Inches(1.5), Inches(3.3), Inches(10.2), Inches(0.8), 17, MUTED, False, PP_ALIGN.CENTER)


def _render_bullets(slide, title: str, bullets: list[str]) -> None:
    _textbox(slide, title, Inches(0.8), Inches(0.45), Inches(11.8), Inches(0.8), 27, WHITE, True)
    box = slide.shapes.add_textbox(Inches(1), Inches(1.55), Inches(11.1), Inches(5.1))
    frame = box.text_frame; frame.clear(); frame.word_wrap = True
    for index, text in enumerate(bullets[:6]):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = _bounded(text, MAX_BULLET_CHARS); paragraph.level = 0
        paragraph.font.name = "Aptos"; paragraph.font.size = Pt(20); paragraph.font.color.rgb = WHITE
        paragraph.space_after = Pt(14)


def _render_metrics(slide, item: KeyMetricsSlide) -> None:
    _textbox(slide, item.title, Inches(0.8), Inches(0.45), Inches(11.8), Inches(0.8), 27, WHITE, True)
    count = len(item.metrics); card_width = min(2.75, 10.8 / count); start = (13.333 - (card_width * count + 0.25 * (count - 1))) / 2
    for index, metric in enumerate(item.metrics):
        left = Inches(start + index * (card_width + 0.25))
        shape = slide.shapes.add_shape(5, left, Inches(2.05), Inches(card_width), Inches(2.8))
        shape.fill.solid(); shape.fill.fore_color.rgb = BLUE; shape.line.fill.background()
        _textbox(slide, metric.value, left + Inches(0.18), Inches(2.45), Inches(card_width - 0.36), Inches(0.85), 25, YELLOW, True, PP_ALIGN.CENTER)
        _textbox(slide, metric.label, left + Inches(0.18), Inches(3.5), Inches(card_width - 0.36), Inches(0.8), 14, WHITE, False, PP_ALIGN.CENTER)


def _render_table(slide, item: TableSlide) -> None:
    if any(len(row) != len(item.headers) for row in item.rows):
        raise PresentationGenerationError("Svi redovi tabele moraju imati isti broj kolona kao zaglavlje.")
    _textbox(slide, item.title, Inches(0.8), Inches(0.4), Inches(11.8), Inches(0.8), 26, WHITE, True)
    shape = slide.shapes.add_table(len(item.rows) + 1, len(item.headers), Inches(0.75), Inches(1.45), Inches(11.85), Inches(5.35))
    table = shape.table
    for row_index, values in enumerate([item.headers, *item.rows]):
        for column_index, value in enumerate(values):
            cell = table.cell(row_index, column_index); cell.text = _bounded(value, MAX_TABLE_CELL_CHARS)
            cell.fill.solid(); cell.fill.fore_color.rgb = BLUE if row_index == 0 else RGBColor(0x18, 0x22, 0x36)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.name = "Aptos"; paragraph.font.size = Pt(13); paragraph.font.color.rgb = YELLOW if row_index == 0 else WHITE
                paragraph.font.bold = row_index == 0


def _bounded(value: str, maximum: int) -> str:
    value = value.strip()
    return value if len(value) <= maximum else value[: maximum - 1].rstrip() + "…"


def _safe_filename(title: str) -> str:
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")[:80] or "presentation"
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"askhype_{slug}_{stamp}.pptx"
