from typing import Protocol

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.attachments import ImageAttachment
from app.schemas.documents import ExtractedDocument
from app.schemas.xlsx_transform import TransformationPlan
from app.services.hype_retrieval import HypeContext
from app.services.public_sources import PublicSourceContext


class AIProvider(Protocol):
    provider_name: str

    async def generate_chat_response(
        self,
        request: ChatRequest,
        *,
        hype_context: HypeContext | None = None,
        source_context: PublicSourceContext | None = None,
        images: list[ImageAttachment] | None = None,
    ) -> ChatResponse:
        """Generate a structured chat response for AskHype."""

    async def generate_document_answer(
        self,
        prompt: str,
        document: ExtractedDocument,
    ) -> str:
        """Answer a question using only extracted uploaded-document content."""

    async def generate_xlsx_transformation_plan(
        self, instruction: str, document: ExtractedDocument
    ) -> TransformationPlan:
        """Convert a user instruction into one allowlisted XLSX operation."""
