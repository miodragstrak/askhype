from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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
from app.schemas.generative_svg import ArtCharacter, ArtDirection, ArtObject, StoryboardPlan, StoryboardResponse, StoryboardSceneResponse, TimelineBeat

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderedStoryboardScene:
    response: StoryboardSceneResponse
    scene_family: str
    element_count: int
    css_keyframes: int
    render_seconds: float
    quality_passed: bool


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

    async def generate_storyboard(self, prompt: str, duration_seconds: int, identity: RequestIdentity, reference_image: PreparedReferenceImage | None = None) -> StoryboardResponse:
        if identity.user_id is None:
            raise PermissionError("Authentication required.")
        event_id = uuid4()
        quota = await self.repository.reserve(event_id=event_id, user_id=identity.user_id, limit=settings.animation_daily_limit)
        started = time.monotonic()
        try:
            plan = await self.provider.generate_storyboard(prompt, duration_seconds)
            if reference_image is not None:
                reference = await self.provider.analyze_reference(reference_image)
                plan = plan.model_copy(update={"shared_art_direction": merge_reference_art_direction(plan.shared_art_direction, reference)})
            rendered_scenes = render_storyboard_plan(plan)
            scenes = [item.response for item in rendered_scenes]
        except Exception as exc:
            category = "artifact_quality_failed" if isinstance(exc, SvgValidationError) and exc.code == "artifact_quality_failed" else "invalid_animation_artifact" if isinstance(exc, (SvgValidationError, ValueError)) else "provider_timeout" if isinstance(exc, TimeoutError) else "animation_failed"
            await self.repository.finalize(event_id, status="failed", failure_category=category)
            raise
        await self.repository.finalize(event_id, status="completed")
        return StoryboardResponse(title=plan.title, total_duration_seconds=plan.total_duration_seconds, scenes=scenes, generation_seconds=round(time.monotonic() - started, 3), remaining_quota=quota["remaining"])


def render_storyboard_plan(plan: StoryboardPlan) -> list[RenderedStoryboardScene]:
    rendered_scenes: list[RenderedStoryboardScene] = []
    for scene in plan.scenes:
        started = time.monotonic()
        direction = _scene_direction(plan, scene.id)
        rendered = render_glow_scene(direction)
        sanitized = sanitize_svg(rendered.svg, duration_seconds=scene.duration_seconds)
        quality = validate_svg_quality(sanitized)
        if not quality.passed:
            raise SvgValidationError("artifact_quality_failed", safe_quality_feedback(quality))
        rendered_scenes.append(RenderedStoryboardScene(
            response=StoryboardSceneResponse(
                id=scene.id, duration_seconds=scene.duration_seconds,
                transition_in=scene.transition_in, transition_out=scene.transition_out,
                svg=sanitized.content,
            ),
            scene_family=rendered.scene_family,
            element_count=sanitized.element_count,
            css_keyframes=sanitized.css_keyframes,
            render_seconds=time.monotonic() - started,
            quality_passed=True,
        ))
    return rendered_scenes


def _scene_direction(plan: StoryboardPlan, scene_id: str) -> ArtDirection:
    scene = next(item for item in plan.scenes if item.id == scene_id)
    shared = plan.shared_art_direction
    subjects = {subject.id: subject for subject in plan.recurring_subjects}
    characters = [ArtCharacter(name=subjects[item].name, role=scene.action, appearance=subjects[item].appearance) for item in scene.subject_ids if subjects[item].kind != "object"]
    objects = [ArtObject(name=subjects[item].name, description=subjects[item].appearance) for item in scene.subject_ids if subjects[item].kind == "object"]
    return shared.model_copy(update={
        "title": f"{plan.title} — {scene.id}", "duration_seconds": scene.duration_seconds,
        "scene_description": scene.description, "characters": characters, "objects": objects,
        "background_description": scene.environment, "composition": scene.composition,
        "mood": scene.mood, "timeline_beats": [TimelineBeat(start=0, duration=scene.duration_seconds, description=scene.description, motion=scene.action)],
    })
