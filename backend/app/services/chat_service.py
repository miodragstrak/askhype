from app.core.config import settings
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockAIProvider
from app.schemas.chat import ChatRequest, ChatResponse


class UnsupportedAIProviderError(RuntimeError):
    pass


class ChatService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or self._provider_from_settings()

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        return await self.provider.generate_chat_response(request)

    def _provider_from_settings(self) -> AIProvider:
        if settings.ai_provider == "mock":
            return MockAIProvider()
        if settings.ai_provider == "gemini":
            return GeminiProvider()

        raise UnsupportedAIProviderError(
            f"Unsupported AI_PROVIDER value: {settings.ai_provider}"
        )
