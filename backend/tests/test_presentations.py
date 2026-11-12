import asyncio
import io
from uuid import uuid4

import httpx
import pytest
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.main import app
from app.schemas.presentations import (
    BulletsSlide, ConclusionSlide, KeyMetricsSlide, MetricCard, PresentationPlan,
    PresentationPlanEnvelope, SectionSlide, TableSlide, TitleSlide,
)
from app.services.presentation_generation import (
    PresentationGenerationError, PresentationGenerationService, PresentationResult,
    render_presentation, requested_slide_count,
)


def sample_plan() -> PresentationPlan:
    return PresentationPlan(
        title="Q1 poslovni rezultati", subtitle="Pregled ključnih pokazatelja",
        slides=[
            TitleSlide(type="title", title="Q1 poslovni rezultati", subtitle="Pregled ključnih pokazatelja"),
            SectionSlide(type="section", title="Pregled", subtitle="Najvažnije teme"),
            BulletsSlide(type="bullets", title="Ključni rezultati", bullets=["Prihod je 3.750.000 RSD", "Trošak je 2.380.000 RSD"]),
            KeyMetricsSlide(type="key_metrics", title="Pokazatelji", metrics=[MetricCard(label="Prihod", value="3,75M RSD"), MetricCard(label="Klijenti", value="51")]),
            TableSlide(type="table", title="Rezultati", headers=["Region", "Prihod"], rows=[["Beograd", "2.600.000"], ["Novi Sad", "1.150.000"]]),
            ConclusionSlide(type="conclusion", title="Zaključak", bullets=["Cilj je premašen za 150.000 RSD"]),
        ],
    )


def test_valid_pptx_reopens_with_all_supported_slide_types() -> None:
    content = render_presentation(sample_plan())
    presentation = Presentation(io.BytesIO(content))
    assert len(presentation.slides) == 6
    assert presentation.slide_width / presentation.slide_height == pytest.approx(16 / 9, rel=0.01)
    text = "\n".join(shape.text for slide in presentation.slides for shape in slide.shapes if hasattr(shape, "text"))
    table_text = "\n".join(
        cell.text for slide in presentation.slides for shape in slide.shapes if shape.has_table
        for row in shape.table.rows for cell in row.cells
    )
    text += "\n" + table_text
    for expected in ["Q1 poslovni rezultati", "Ključni rezultati", "Prihod", "Beograd", "Zaključak"]:
        assert expected in text


@pytest.mark.parametrize(("prompt", "expected", "warning"), [
    ("Napravi prezentaciju", 6, False),
    ("Napravi 2 slajda", 3, True),
    ("Napravi prezentaciju od 20 slajdova", 12, True),
    ("Napravi 8 slides", 8, False),
])
def test_requested_slide_count_is_bounded(prompt, expected, warning) -> None:
    count, warnings = requested_slide_count(prompt)
    assert count == expected
    assert bool(warnings) is warning


def test_plan_text_and_table_dimensions_are_bounded() -> None:
    payload = sample_plan().model_dump()
    payload["slides"][2]["bullets"] = ["x" * 181]
    with pytest.raises(ValidationError): PresentationPlan.model_validate(payload)
    payload = sample_plan().model_dump()
    payload["slides"][4]["rows"] = [["a", "b"]] * 9
    with pytest.raises(ValidationError): PresentationPlan.model_validate(payload)


def test_invalid_slide_type_and_malformed_table_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PresentationPlanEnvelope.model_validate({"plan": {"title": "X", "slides": [{"type": "video"}] * 3}})
    plan = sample_plan()
    plan.slides[4] = TableSlide(type="table", title="Loša tabela", headers=["A", "B"], rows=[["samo A"]])
    with pytest.raises(PresentationGenerationError, match="isti broj kolona"):
        render_presentation(plan)


def _docx() -> bytes:
    document = Document(); document.add_paragraph("Beta plan ima budžet 1000 RSD.")
    output = io.BytesIO(); document.save(output); return output.getvalue()


def _xlsx() -> bytes:
    workbook = Workbook(); workbook.active.append(["Prihod", 3750000])
    output = io.BytesIO(); workbook.save(output); workbook.close(); return output.getvalue()


def _pdf() -> bytes:
    writer = PdfWriter(); page = writer.add_blank_page(612, 792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject(); stream.set_data(b"BT /F1 12 Tf 72 720 Td (Beta plan budget 1000 RSD) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output); return output.getvalue()


SOURCES = [
    ("brief.pdf", "application/pdf", _pdf),
    ("brief.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", _docx),
    ("rezultati.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", _xlsx),
    ("rezultati.csv", "text/csv", lambda: b"metrika,vrednost\nprihod,3750000\n"),
]


async def _post(anonymous_id: str, source=None):
    files = [("prompt", (None, "Napravi prezentaciju od 6 slajdova"))]
    if source:
        files.append(("file", (source[0], source[2](), source[1])))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/presentations/generate", headers={"X-Anonymous-ID": anonymous_id},
            files=files,
        )
        usage = await client.get("/api/usage", headers={"X-Anonymous-ID": anonymous_id})
        return response, usage


@pytest.mark.parametrize("source", [None, *SOURCES])
def test_endpoint_supports_prompt_and_each_document_type(monkeypatch, source) -> None:
    seen = {}
    async def generate(self, prompt, document):
        seen["type"] = document.file_type if document else None
        content = render_presentation(sample_plan())
        return PresentationResult(content, "askhype_q1.pptx", 6, "Prezentacija je napravljena.", ())
    monkeypatch.setattr(PresentationGenerationService, "generate", generate)
    response, usage = asyncio.run(_post(str(uuid4()), source))
    assert response.status_code == 200
    assert seen["type"] == (source[0].rsplit(".", 1)[1] if source else None)
    assert response.headers["X-AskHype-Presentation-Slide-Count"] == "6"
    assert len(Presentation(io.BytesIO(response.content)).slides) == 6
    assert usage.json()["used"] == 1


def test_unsupported_file_fails_before_quota() -> None:
    source = ("notes.txt", "text/plain", lambda: b"not supported")
    response, usage = asyncio.run(_post(str(uuid4()), source))
    assert response.status_code == 400
    assert usage.json()["used"] == 0


def test_invalid_plan_failure_does_not_count_quota(monkeypatch) -> None:
    async def generate(self, prompt, document):
        raise PresentationGenerationError("Plan nije ispravan.")
    monkeypatch.setattr(PresentationGenerationService, "generate", generate)
    response, usage = asyncio.run(_post(str(uuid4())))
    assert response.status_code == 400
    assert usage.json()["used"] == 0
