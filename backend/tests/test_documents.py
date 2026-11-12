import asyncio
import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from docx import Document
from openpyxl import Workbook
from openpyxl import load_workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from starlette.datastructures import UploadFile

from app.main import app
from app.schemas.documents import DocumentAnalysisResponse
from app.services.document_analysis import DocumentAnalysisService
from app.services.document_extraction import (
    MAX_DOCUMENT_BYTES,
    DocumentValidationError,
    extract_document,
)


def _pdf_bytes(text: str = "Prihod je porastao za deset procenata.") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _docx_bytes() -> bytes:
    document = Document()
    document.add_heading("Kvartalni izveštaj", level=1)
    document.add_paragraph("Prodaja je porasla u drugom kvartalu.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Region"
    table.rows[0].cells[1].text = "Prihod"
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Prodaja"
    sheet.append(["Region", "Prihod"])
    sheet.append(["Srbija", 1250])
    workbook.create_sheet("Troškovi").append(["Marketing", 300])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _xlsx_without_dimension_metadata() -> bytes:
    source = io.BytesIO(_xlsx_bytes())
    output = io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as rewritten:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = re.sub(br"<dimension[^>]*/>", b"", content, count=1)
            rewritten.writestr(item, content)
    return output.getvalue()


def test_pdf_text_extraction() -> None:
    result = extract_document(_pdf_bytes(), "izvestaj.pdf", "application/pdf")
    assert "Prihod je porastao" in result.text
    assert result.metadata.page_count == 1
    assert result.file_type == "pdf"


def test_docx_text_and_structure_extraction() -> None:
    result = extract_document(
        _docx_bytes(), "izvestaj.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert "# Kvartalni izveštaj" in result.text
    assert "[Tabela 1]" in result.text
    assert "Region | Prihod" in result.text


def test_xlsx_sheet_names_and_cells_are_extracted() -> None:
    result = extract_document(
        _xlsx_bytes(), "podaci.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert result.metadata.sheet_names == ["Prodaja", "Troškovi"]
    assert "Srbija | 1250" in result.text
    assert result.metadata.rows_processed == 3


def test_xlsx_without_dimension_metadata_is_extracted() -> None:
    body = _xlsx_without_dimension_metadata()
    workbook = load_workbook(io.BytesIO(body), read_only=True)
    try:
        assert workbook["Prodaja"].max_row is None
        assert workbook["Prodaja"].max_column is None
    finally:
        workbook.close()

    result = extract_document(
        body, "bez-dimenzija.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert result.metadata.sheet_names == ["Prodaja", "Troškovi"]
    assert "[Radni list: Prodaja]" in result.text
    assert "Srbija | 1250" in result.text
    assert result.metadata.rows_processed == 3
    assert result.metadata.columns_processed == 2


def test_xlsx_iteration_enforces_row_and_column_limits() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Veliki list"
    for row_number in range(1, 202):
        sheet.cell(row=row_number, column=1, value=f"red-{row_number}")
    for column_number in range(2, 51):
        sheet.cell(row=1, column=column_number, value=f"kolona-{column_number}")
    sheet.cell(row=1, column=51, value="izvan-limita")
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()

    result = extract_document(
        output.getvalue(), "veliki.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert result.metadata.rows_processed == 200
    assert result.metadata.columns_processed == 50
    assert result.metadata.truncated is True
    assert "Po radnom listu obrađeno je najviše 200 redova." in result.warnings
    assert "Po redu je obrađeno najviše 50 kolona." in result.warnings
    assert "red-201" not in result.text
    assert "izvan-limita" not in result.text


def test_csv_utf8_and_common_delimiter_are_extracted() -> None:
    result = extract_document("grad;broj\nBeograd;42\n".encode(), "podaci.csv", "text/csv")
    assert "1: grad | broj" in result.text
    assert "2: Beograd | 42" in result.text
    assert result.metadata.columns_processed == 2


@pytest.mark.parametrize(
    ("body", "filename", "mime", "message"),
    [
        (b"hello", "notes.txt", "text/plain", "Podržani su samo"),
        (b"not pdf", "fake.pdf", "application/pdf", "nije ispravan PDF"),
        (_pdf_bytes(), "fake.csv", "text/csv", "nije ispravan CSV"),
        (_docx_bytes(), "fake.docx", "application/pdf", "ne odgovara"),
    ],
)
def test_unsupported_or_spoofed_document_is_rejected(body, filename, mime, message) -> None:
    with pytest.raises(DocumentValidationError, match=message):
        extract_document(body, filename, mime)


def test_oversized_and_empty_documents_are_rejected() -> None:
    with pytest.raises(DocumentValidationError, match="15 MB") as oversized:
        extract_document(b"x" * (MAX_DOCUMENT_BYTES + 1), "large.csv", "text/csv")
    assert oversized.value.status_code == 413
    with pytest.raises(DocumentValidationError, match="prazan"):
        extract_document(b"", "empty.csv", "text/csv")


def test_image_only_pdf_returns_clear_ocr_limitation() -> None:
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(DocumentValidationError, match="OCR nije podržan"):
        extract_document(output.getvalue(), "scan.pdf", "application/pdf")


def test_processing_creates_no_temporary_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    extract_document(_docx_bytes(), "safe.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert set(tmp_path.iterdir()) == before


def test_endpoint_closes_spooled_upload_file(monkeypatch) -> None:
    closed: list[str | None] = []
    original_close = UploadFile.close

    async def tracked_close(self):
        closed.append(self.filename)
        await original_close(self)

    monkeypatch.setattr(UploadFile, "close", tracked_close)
    response = asyncio.run(_post_document(b"naziv,vrednost\nPrihod,1250\n", "cleanup.csv", "text/csv"))
    assert response.status_code == 200
    assert "cleanup.csv" in closed


async def _post_document(body: bytes, filename: str, mime: str, prompt: str = "Šta piše?"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/documents/analyze",
            headers={"X-Anonymous-ID": str(uuid4())},
            data={"prompt": prompt},
            files={"file": (filename, body, mime)},
        )


def test_document_endpoint_returns_typed_grounded_response_and_counts_one_prompt(monkeypatch) -> None:
    async def analyze(self, prompt, document):
        assert prompt == "Koliki je prihod?"
        assert "Srbija | 1250" in document.text
        return DocumentAnalysisResponse(
            filename=document.filename,
            file_type=document.file_type,
            answer="Dokument navodi prihod 1250 za Srbiju.",
            extracted_metadata=document.metadata,
            warnings=list(document.warnings),
            generated_at=datetime.now(UTC),
        )

    monkeypatch.setattr(DocumentAnalysisService, "analyze", analyze)
    response = asyncio.run(_post_document(
        _xlsx_bytes(), "../podaci.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Koliki je prihod?",
    ))
    assert response.status_code == 200
    assert response.json()["filename"] == "podaci.xlsx"
    assert response.json()["answer"] == "Dokument navodi prihod 1250 za Srbiju."
    assert response.headers["X-AskHype-Usage-Used"] == "1"


def test_invalid_document_is_rejected_before_quota_reservation() -> None:
    anonymous_id = str(uuid4())

    async def request_pair():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            failed = await client.post(
                "/api/documents/analyze",
                headers={"X-Anonymous-ID": anonymous_id},
                data={"prompt": "Analiziraj"},
                files={"file": ("bad.pdf", b"not pdf", "application/pdf")},
            )
            usage = await client.get("/api/usage", headers={"X-Anonymous-ID": anonymous_id})
            return failed, usage

    failed, usage = asyncio.run(request_pair())
    assert failed.status_code == 400
    assert usage.json()["used"] == 0

