from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentType = Literal["pdf", "docx", "xlsx", "csv"]


class DocumentMetadata(BaseModel):
    page_count: int | None = None
    sheet_names: list[str] = Field(default_factory=list)
    rows_processed: int | None = None
    columns_processed: int | None = None
    extracted_characters: int
    truncated: bool = False


class DocumentAnalysisResponse(BaseModel):
    filename: str
    file_type: DocumentType
    answer: str
    extracted_metadata: DocumentMetadata
    warnings: list[str]
    generated_at: datetime


@dataclass(frozen=True)
class ExtractedDocument:
    filename: str
    file_type: DocumentType
    text: str
    metadata: DocumentMetadata
    warnings: tuple[str, ...] = ()

