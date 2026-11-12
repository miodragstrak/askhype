from datetime import UTC, datetime

from app.core.config import settings
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockAIProvider
from app.schemas.documents import DocumentAnalysisResponse, ExtractedDocument
from app.services.chat_service import UnsupportedAIProviderError


class DocumentAnalysisService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or self._provider_from_settings()

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    async def analyze(self, prompt: str, document: ExtractedDocument) -> DocumentAnalysisResponse:
        answer = await self.provider.generate_document_answer(prompt, document)
        return DocumentAnalysisResponse(
            filename=document.filename,
            file_type=document.file_type,
            answer=answer,
            extracted_metadata=document.metadata,
            warnings=list(document.warnings),
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    def _provider_from_settings() -> AIProvider:
        if settings.ai_provider == "mock":
            return MockAIProvider()
        if settings.ai_provider == "gemini":
            return GeminiProvider()
        raise UnsupportedAIProviderError(f"Unsupported AI_PROVIDER value: {settings.ai_provider}")

