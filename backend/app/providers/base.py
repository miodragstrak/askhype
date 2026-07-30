from typing import Protocol

from app.schemas.chat import ChatRequest, ChatResponse


class AIProvider(Protocol):
    async def generate_chat_response(self, request: ChatRequest) -> ChatResponse:
        """Generate a structured chat response for AskHype."""
