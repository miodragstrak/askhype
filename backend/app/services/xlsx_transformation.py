from app.core.config import settings
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockAIProvider
from app.schemas.documents import ExtractedDocument
from app.services.chat_service import UnsupportedAIProviderError
from app.services.xlsx_transform import TransformationResult, transform_workbook


class XlsxTransformationService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or self._provider_from_settings()

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    async def transform(
        self, instruction: str, body: bytes, filename: str, document: ExtractedDocument
    ) -> TransformationResult:
        plan = await self.provider.generate_xlsx_transformation_plan(instruction, document)
        return transform_workbook(body, filename, plan)

    @staticmethod
    def _provider_from_settings() -> AIProvider:
        if settings.ai_provider == "mock":
            return MockAIProvider()
        if settings.ai_provider == "gemini":
            return GeminiProvider()
        raise UnsupportedAIProviderError(f"Unsupported AI_PROVIDER value: {settings.ai_provider}")
