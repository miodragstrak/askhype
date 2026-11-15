from __future__ import annotations

import time
from uuid import uuid4

from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.providers.generative_svg import GenerativeSvgProvider
from app.renderers.reference_image import PreparedReferenceImage
from app.renderers.svg_sanitizer import SvgValidationError
from app.repositories.animation_repository import AnimationUsageRepository
from app.schemas.generative_svg import GenerativeSvgResponse


class GenerativeSvgGenerationService:
    def __init__(self, repository: AnimationUsageRepository, provider: GenerativeSvgProvider) -> None:
        self.repository, self.provider = repository, provider

    async def generate(
        self,
        prompt: str,
        identity: RequestIdentity,
        reference_image: PreparedReferenceImage | None = None,
    ) -> GenerativeSvgResponse:
        if identity.user_id is None:
            raise PermissionError("Authentication required.")
        event_id = uuid4()
        quota = await self.repository.reserve(
            event_id=event_id,
            user_id=identity.user_id,
            limit=settings.animation_daily_limit,
        )
        started = time.monotonic()
        try:
            artifact = await self.provider.generate(prompt, reference_image)
        except Exception as exc:
            category = "invalid_animation_artifact" if isinstance(exc, SvgValidationError) else "animation_failed"
            await self.repository.finalize(event_id, status="failed", failure_category=category)
            raise
        await self.repository.finalize(event_id, status="completed")
        return GenerativeSvgResponse(
            svg=artifact.svg.content,
            has_reference=artifact.reference_analysis is not None,
            generation_seconds=round(time.monotonic() - started, 3),
            attempts=artifact.artifact_attempts,
            remaining_quota=quota["remaining"],
        )
