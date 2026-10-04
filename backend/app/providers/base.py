from typing import Protocol

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.hype_retrieval import HypeContext


class AIProvider(Protocol):
    async def generate_chat_response(self, request: ChatRequest, *, hype_context: HypeContext | None = None) -> ChatResponse:
        """Generate a structured chat response for AskHype."""
