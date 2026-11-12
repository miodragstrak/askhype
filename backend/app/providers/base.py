from typing import Protocol

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.attachments import ImageAttachment
from app.schemas.documents import ExtractedDocument
from app.schemas.xlsx_transform import TransformationPlan
from app.schemas.presentations import PresentationPlan
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

    async def generate_presentation_plan(
        self, prompt: str, slide_count: int, document: ExtractedDocument | None
    ) -> PresentationPlan:
        """Create a strict presentation plan, optionally grounded in one document."""
