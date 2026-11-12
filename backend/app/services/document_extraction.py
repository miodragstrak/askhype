import csv
import io
import re
import zipfile
from pathlib import PurePath

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from app.schemas.documents import DocumentMetadata, DocumentType, ExtractedDocument

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
MAX_EXTRACTED_CHARS = 80_000
MAX_PDF_PAGES = 100
MAX_SPREADSHEET_SHEETS = 5
MAX_SPREADSHEET_ROWS = 200
MAX_SPREADSHEET_COLUMNS = 50
MAX_CSV_ROWS = 1_000
MAX_ARCHIVE_MEMBERS = 2_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

_MIME_TYPES: dict[DocumentType, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    "xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    "csv": frozenset({"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"}),
}


class DocumentValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        self.status_code = status_code
        super().__init__(message)


class _TextCollector:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False

    def add(self, value: object) -> bool:
        text = _clean_text(str(value))
        if not text:
            return True
        separator = "\n" if self.parts else ""
        remaining = MAX_EXTRACTED_CHARS - self.length - len(separator)
        if remaining <= 0:
            self.truncated = True
            return False
        if len(text) > remaining:
            text = text[:remaining].rstrip()
            self.truncated = True
        self.parts.append(separator + text)
        self.length += len(separator) + len(text)
        return not self.truncated

    @property
    def text(self) -> str:
        return "".join(self.parts)


def extract_document(
    body: bytes,
    filename: str | None,
    declared_mime: str | None,
) -> ExtractedDocument:
    safe_name, file_type = _validate_upload(body, filename, declared_mime)
    try:
        if file_type == "pdf":
            return _extract_pdf(body, safe_name)
        if file_type == "docx":
            _validate_office_archive(body, "word/document.xml")
            return _extract_docx(body, safe_name)
        if file_type == "xlsx":
            _validate_office_archive(body, "xl/workbook.xml")
            return _extract_xlsx(body, safe_name)
        return _extract_csv(body, safe_name)
    except DocumentValidationError:
        raise
    except Exception as exc:
        raise DocumentValidationError("Dokument nije moguće pročitati ili je oštećen.") from exc


def _validate_upload(
    body: bytes,
    filename: str | None,
    declared_mime: str | None,
) -> tuple[str, DocumentType]:
    if not body:
        raise DocumentValidationError("Dokument je prazan.")
    if len(body) > MAX_DOCUMENT_BYTES:
        raise DocumentValidationError("Dokument je veći od dozvoljenih 15 MB.", status_code=413)

    safe_name = _safe_filename(filename)
    extension = PurePath(safe_name).suffix.casefold().lstrip(".")
    if extension not in _MIME_TYPES:
        raise DocumentValidationError("Podržani su samo PDF, DOCX, XLSX i CSV dokumenti.")
    file_type: DocumentType = extension  # type: ignore[assignment]
    mime = (declared_mime or "").split(";", 1)[0].strip().casefold()
    if mime not in _MIME_TYPES[file_type]:
        raise DocumentValidationError("Tip dokumenta ne odgovara njegovoj ekstenziji.")

    if file_type == "pdf" and not body.startswith(b"%PDF-"):
        raise DocumentValidationError("Sadržaj dokumenta nije ispravan PDF.")
    if file_type in {"docx", "xlsx"} and not body.startswith(b"PK"):
        raise DocumentValidationError("Sadržaj dokumenta ne odgovara Office formatu.")
    if file_type == "csv" and (b"\x00" in body[:4096] or body.startswith((b"%PDF-", b"PK"))):
        raise DocumentValidationError("Sadržaj dokumenta nije ispravan CSV tekst.")
    return safe_name, file_type


def _safe_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/").split("/")[-1]
    normalized = "".join(char for char in normalized if char.isprintable()).strip(" .")
    if not normalized:
        raise DocumentValidationError("Nedostaje ispravan naziv dokumenta.")
    return normalized[:255]


def _validate_office_archive(body: bytes, required_member: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise DocumentValidationError("Office dokument sadrži previše stavki.")
            if required_member not in {item.filename for item in members}:
                raise DocumentValidationError("Sadržaj dokumenta ne odgovara njegovoj ekstenziji.")
            if any(item.flag_bits & 0x1 for item in members):
                raise DocumentValidationError("Šifrovani Office dokumenti nisu podržani.")
            if sum(item.file_size for item in members) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise DocumentValidationError("Raspakovan dokument je prevelik za bezbednu obradu.")
    except zipfile.BadZipFile as exc:
        raise DocumentValidationError("Office dokument je oštećen.") from exc


def _extract_pdf(body: bytes, filename: str) -> ExtractedDocument:
    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted:
        raise DocumentValidationError("Šifrovani PDF dokumenti nisu podržani.")
    collector = _TextCollector()
    warnings: list[str] = []
    total_pages = len(reader.pages)
    for index, page in enumerate(reader.pages[:MAX_PDF_PAGES]):
        if not collector.add(f"[Strana {index + 1}]\n{page.extract_text() or ''}"):
            break
    truncated = collector.truncated or total_pages > MAX_PDF_PAGES
    if total_pages > MAX_PDF_PAGES:
        warnings.append(f"Obrađeno je prvih {MAX_PDF_PAGES} PDF strana.")
    if collector.truncated:
        warnings.append("Izdvojeni tekst je skraćen zbog ograničenja konteksta.")
    if sum(char.isalpha() for char in re.sub(r"\[Strana \d+\]", "", collector.text)) < 5:
        raise DocumentValidationError("PDF nema tekst koji je moguće izdvojiti. OCR nije podržan.")
    return _result(filename, "pdf", collector, warnings, page_count=total_pages, truncated=truncated)


def _extract_docx(body: bytes, filename: str) -> ExtractedDocument:
    document = Document(io.BytesIO(body))
    collector = _TextCollector()
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        prefix = "# " if (paragraph.style and paragraph.style.name.startswith("Heading")) else ""
        if not collector.add(prefix + text):
            break
    if not collector.truncated:
        for table_index, table in enumerate(document.tables, start=1):
            if not collector.add(f"[Tabela {table_index}]"):
                break
            for row in table.rows:
                if not collector.add(" | ".join(cell.text.strip() for cell in row.cells)):
                    break
            if collector.truncated:
                break
    warnings = ["Izdvojeni tekst je skraćen zbog ograničenja konteksta."] if collector.truncated else []
    if not _has_meaningful_text(collector.text):
        raise DocumentValidationError("DOCX dokument ne sadrži tekst za analizu.")
    return _result(filename, "docx", collector, warnings, truncated=collector.truncated)


def _extract_xlsx(body: bytes, filename: str) -> ExtractedDocument:
    workbook = load_workbook(io.BytesIO(body), read_only=True, data_only=False, keep_links=False)
    collector = _TextCollector()
    warnings: list[str] = []
    all_sheets = workbook.sheetnames
    selected_sheets = all_sheets[:MAX_SPREADSHEET_SHEETS]
    rows_processed = 0
    columns_processed = 0
    row_limited = False
    column_limited = False
    try:
        for sheet_name in selected_sheets:
            sheet = workbook[sheet_name]
            if not collector.add(f"[Radni list: {sheet_name}]"):
                break
            rows = sheet.iter_rows(values_only=True)
            for row_index, row in enumerate(rows, start=1):
                if row_index > MAX_SPREADSHEET_ROWS:
                    row_limited = True
                    break
                column_limited = column_limited or any(
                    _cell_text(value) for value in row[MAX_SPREADSHEET_COLUMNS:]
                )
                values = [_cell_text(value) for value in row[:MAX_SPREADSHEET_COLUMNS]]
                while values and not values[-1]:
                    values.pop()
                if not values:
                    continue
                rows_processed += 1
                columns_processed = max(columns_processed, len(values))
                if not collector.add(f"{row_index}: " + " | ".join(values)):
                    break
            if collector.truncated:
                break
    finally:
        workbook.close()
    limited = len(all_sheets) > MAX_SPREADSHEET_SHEETS
    if limited:
        warnings.append(f"Obrađeno je prvih {MAX_SPREADSHEET_SHEETS} radnih listova.")
    if row_limited:
        warnings.append(f"Po radnom listu obrađeno je najviše {MAX_SPREADSHEET_ROWS} redova.")
        limited = True
    if column_limited:
        warnings.append(f"Po redu je obrađeno najviše {MAX_SPREADSHEET_COLUMNS} kolona.")
        limited = True
    if collector.truncated:
        warnings.append("Izdvojeni tekst je skraćen zbog ograničenja konteksta.")
    if not _has_meaningful_text(collector.text):
        raise DocumentValidationError("XLSX dokument ne sadrži ćelije za analizu.")
    return _result(
        filename, "xlsx", collector, warnings, sheet_names=selected_sheets,
        rows_processed=rows_processed, columns_processed=columns_processed,
        truncated=limited or collector.truncated,
    )
def _extract_csv(body: bytes, filename: str) -> ExtractedDocument:
    try:
        decoded = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentValidationError("CSV mora biti kodiran kao UTF-8.") from exc
    sample = decoded[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    collector = _TextCollector()
    rows_processed = 0
    columns_processed = 0
    column_limited = False
    reader = csv.reader(io.StringIO(decoded, newline=""), dialect)
    for row_index, row in enumerate(reader, start=1):
        if row_index > MAX_CSV_ROWS:
            break
        column_limited = column_limited or len(row) > MAX_SPREADSHEET_COLUMNS
        values = [_clean_text(value) for value in row[:MAX_SPREADSHEET_COLUMNS]]
        rows_processed += 1
        columns_processed = max(columns_processed, len(values))
        if not collector.add(f"{row_index}: " + " | ".join(values)):
            break
    row_limited = rows_processed == MAX_CSV_ROWS and next(reader, None) is not None
    warnings: list[str] = []
    if row_limited:
        warnings.append(f"Obrađeno je prvih {MAX_CSV_ROWS} CSV redova.")
    if column_limited:
        warnings.append(f"Po redu je obrađeno najviše {MAX_SPREADSHEET_COLUMNS} kolona.")
    if collector.truncated:
        warnings.append("Izdvojeni tekst je skraćen zbog ograničenja konteksta.")
    if not _has_meaningful_text(collector.text):
        raise DocumentValidationError("CSV dokument ne sadrži podatke za analizu.")
    return _result(
        filename, "csv", collector, warnings, rows_processed=rows_processed,
        columns_processed=columns_processed, truncated=row_limited or column_limited or collector.truncated,
    )


def _result(
    filename: str,
    file_type: DocumentType,
    collector: _TextCollector,
    warnings: list[str],
    **metadata: object,
) -> ExtractedDocument:
    return ExtractedDocument(
        filename=filename,
        file_type=file_type,
        text=collector.text,
        metadata=DocumentMetadata(extracted_characters=len(collector.text), **metadata),
        warnings=tuple(warnings),
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", "".join(char for char in value if char.isprintable() or char.isspace())).strip()


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return _clean_text(str(value))


def _has_meaningful_text(value: str) -> bool:
    return any(char.isalnum() for char in value)

