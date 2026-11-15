from __future__ import annotations

import logging
import time
from uuid import uuid4

from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.providers.generative_svg import GenerativeSvgProvider
from app.providers.generative_svg import merge_reference_art_direction
from app.renderers.reference_image import PreparedReferenceImage
from app.renderers.glow_scene_renderer import render_glow_scene
from app.renderers.svg_quality import safe_quality_feedback, validate_svg_quality
from app.renderers.svg_sanitizer import SvgValidationError
from app.renderers.svg_sanitizer import sanitize_svg
from app.repositories.animation_repository import AnimationUsageRepository
from app.schemas.generative_svg import GenerativeSvgResponse

logger = logging.getLogger(__name__)


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
        logger.info("generative_svg_service_started", extra={"stage": "provider_generation"})
        try:
            prompt_direction = await self.provider.generate_art_direction(prompt)
            reference_analysis = None
            direction = prompt_direction
            if reference_image is not None:
                reference_analysis = await self.provider.analyze_reference(reference_image)
                direction = merge_reference_art_direction(prompt_direction, reference_analysis)
            render_started = time.monotonic()
            rendered = render_glow_scene(direction)
            sanitized = sanitize_svg(rendered.svg, duration_seconds=direction.duration_seconds)
            quality = validate_svg_quality(sanitized)
            if not quality.passed:
                raise SvgValidationError("artifact_quality_failed", safe_quality_feedback(quality))
            logger.info(
                "generative_svg_deterministic_render_completed",
                extra={
                    "stage": "deterministic_render",
                    "elapsed_seconds": round(time.monotonic() - render_started, 6),
                    "element_count": sanitized.element_count,
                    "css_keyframes": sanitized.css_keyframes,
                    "quality_passed": True,
                },
            )
        except Exception as exc:
            category = (
                "artifact_quality_failed"
                if isinstance(exc, SvgValidationError) and exc.code == "artifact_quality_failed"
                else "invalid_animation_artifact" if isinstance(exc, SvgValidationError)
                else "provider_timeout" if isinstance(exc, TimeoutError)
                else "animation_failed"
            )
            await self.repository.finalize(event_id, status="failed", failure_category=category)
            logger.info(
                "generative_svg_service_finished",
                extra={
                    "stage": "provider_generation", "outcome": category,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                },
            )
            raise
        logger.info(
            "generative_svg_service_finished",
            extra={
                "stage": "provider_generation", "outcome": "completed",
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        )
        await self.repository.finalize(event_id, status="completed")
        return GenerativeSvgResponse(
            svg=sanitized.content,
            has_reference=reference_analysis is not None,
            generation_seconds=round(time.monotonic() - started, 3),
            attempts=1,
            remaining_quota=quota["remaining"],
        )
