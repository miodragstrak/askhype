from app.core.config import settings
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockAIProvider
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.attachments import ImageAttachment
from app.services.hype_retrieval import HypeRetriever, hype_retriever, hype_topic
from app.services.public_sources import PublicSourceReader, public_source_reader
from app.services.source_response import build_source_response


class UnsupportedAIProviderError(RuntimeError):
    pass


class ChatService:
    def __init__(
        self,
        provider: AIProvider | None = None,
        retriever: HypeRetriever | None = None,
        source_reader: PublicSourceReader | None = None,
    ) -> None:
        self.provider = provider or self._provider_from_settings()
        self.retriever = retriever or hype_retriever
        self.source_reader = source_reader or public_source_reader

    async def generate_response(self, request: ChatRequest, images: list[ImageAttachment] | None = None) -> ChatResponse:
        if hype_topic(request.message):
            context = await self.retriever.retrieve(request.message)
            return await self.provider.generate_chat_response(request, hype_context=context, images=images)
        source_context = await self.source_reader.retrieve(request.message)
        if source_context is not None:
            if not source_context.documents and not images:
                return build_source_response(source_context, request, self.provider.provider_name)
            return await self.provider.generate_chat_response(request, source_context=source_context, images=images)
        return await self.provider.generate_chat_response(request, images=images)

    def _provider_from_settings(self) -> AIProvider:
        if settings.ai_provider == "mock":
            return MockAIProvider()
        if settings.ai_provider == "gemini":
            return GeminiProvider()

        raise UnsupportedAIProviderError(
            f"Unsupported AI_PROVIDER value: {settings.ai_provider}"
        )
