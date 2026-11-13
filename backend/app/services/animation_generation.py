from uuid import uuid4

from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.providers.animation import AnimationProvider
from app.providers.exceptions import (
    AIAnimationPlanError, AIProviderConfigurationError, AIProviderRateLimitError,
    AIProviderResponseError, AIProviderTimeoutError, AIProviderUnavailableError,
)
from app.repositories.animation_repository import AnimationUsageRepository
from app.schemas.animations import AnimationRequest, AnimationResponse


class AnimationGenerationService:
    def __init__(self, repository: AnimationUsageRepository, provider: AnimationProvider) -> None:
        self.repository, self.provider = repository, provider

    async def generate(self, request: AnimationRequest, identity: RequestIdentity) -> AnimationResponse:
        if identity.user_id is None:
            raise PermissionError("Authentication required.")
        event_id = uuid4()
        quota = await self.repository.reserve(
            event_id=event_id, user_id=identity.user_id, limit=settings.animation_daily_limit,
        )
        try:
            plan = await self.provider.generate_plan(request.prompt, request.language)
        except Exception as exc:
            await self.repository.finalize(event_id, status="failed", failure_category=_failure_category(exc))
            raise
        await self.repository.finalize(event_id, status="completed")
        return AnimationResponse(
            animation_id=event_id, title=plan.title, plan=plan, provider=self.provider.provider_name,
            model=self.provider.model, quota=quota,
        )


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, AIProviderRateLimitError): return "provider_rate_limited"
    if isinstance(exc, AIProviderUnavailableError): return "provider_unavailable"
    if isinstance(exc, AIProviderTimeoutError): return "provider_timeout"
    if isinstance(exc, (AIAnimationPlanError, AIProviderResponseError)): return "invalid_animation_plan"
    if isinstance(exc, AIProviderConfigurationError): return "animation_failed"
    return "animation_failed"
