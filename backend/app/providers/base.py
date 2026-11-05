from typing import Protocol

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.attachments import ImageAttachment
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
