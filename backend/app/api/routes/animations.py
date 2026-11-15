import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_animation_provider, get_animation_repository, get_authenticated_identity,
    get_generative_svg_provider,
)
from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.providers.animation import AnimationProvider
from app.providers.exceptions import (
    AIAnimationPlanError, AIProviderConfigurationError, AIProviderRateLimitError,
    AIProviderResponseError, AIProviderTimeoutError, AIProviderUnavailableError,
)
from app.repositories.animation_repository import AnimationLimitReached, AnimationUsageRepository
from app.schemas.animations import AnimationRequest, AnimationResponse
from app.services.animation_generation import AnimationGenerationService
from app.renderers.cartoon_renderer import (
    CartoonRenderError, CartoonRenderTimeout, cleanup_workspace, render_video,
)
from app.providers.generative_svg import GenerativeSvgProvider
from app.renderers.reference_image import MAX_REFERENCE_BYTES, ReferenceImageError, prepare_reference_image
from app.renderers.svg_sanitizer import SvgValidationError
from app.schemas.generative_svg import GenerativeSvgResponse, StoryboardResponse
from app.services.generative_svg_generation import GenerativeSvgGenerationService

router = APIRouter(prefix="/animations", tags=["animations"])


@router.post("/generative-svg", response_model=StoryboardResponse)
async def generate_svg_animation(
    prompt: str = Form(...),
    duration_seconds: int = Form(default=20),
    reference_image: UploadFile | None = File(default=None),
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: AnimationUsageRepository = Depends(get_animation_repository),
    provider: GenerativeSvgProvider | None = Depends(get_generative_svg_provider),
) -> StoryboardResponse:
    if not settings.generative_svg_beta_enabled:
        raise HTTPException(404, detail={"code": "feature_disabled", "message": "AI animacije trenutno nisu dostupne."})
    if provider is None:
        raise HTTPException(503, detail={"code": "provider_unavailable", "message": "AI servis trenutno nije dostupan. Pokušajte ponovo."})
    prompt = prompt.strip()
    if not prompt or len(prompt) > 3000:
        raise HTTPException(422, detail={"code": "invalid_prompt", "message": "Opis animacije je obavezan i može imati najviše 3000 znakova."})
    if duration_seconds not in {10, 15, 20, 30}:
        raise HTTPException(422, detail={"code": "invalid_duration", "message": "Trajanje animacije mora biti 10, 15, 20 ili 30 sekundi."})

    prepared_reference = None
    if reference_image is not None:
        try:
            prepared_reference = prepare_reference_image(await reference_image.read(MAX_REFERENCE_BYTES + 1))
        except ReferenceImageError as exc:
            raise HTTPException(400, detail={"code": "invalid_reference_image", "message": "Referentna slika nije podržana ili je prevelika."}) from exc
        finally:
            await reference_image.close()
    try:
        return await GenerativeSvgGenerationService(repository, provider).generate_storyboard(prompt, duration_seconds, identity, prepared_reference)
    except AnimationLimitReached as exc:
        raise HTTPException(429, detail={
            "code": "animation_daily_quota_reached",
            "message": f"Dostigli ste dnevni limit za animacije ({exc.limit}). Pokušajte ponovo sutra.",
            "used": exc.used, "limit": exc.limit, "remaining": 0, "reset_at": exc.reset_at.isoformat(),
        }) from exc
    except (SvgValidationError, ValueError) as exc:
        raise HTTPException(502, detail={
            "code": "invalid_animation_artifact",
            "message": "Animaciju trenutno nije moguće bezbedno prikazati. Pokušajte ponovo ili pojednostavite opis.",
        }) from exc
    except TimeoutError as exc:
        raise HTTPException(504, detail={"code": "provider_timeout", "message": "Generisanje animacije je isteklo. Pokušajte ponovo."}) from exc
    except PermissionError as exc:
        raise HTTPException(401, detail="Authentication required.") from exc
    except Exception as exc:
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status_code == 429:
            status, code = 429, "provider_rate_limited"
        elif status_code == 400:
            status, code = 502, "invalid_animation_artifact"
        else:
            status, code = 503, "provider_unavailable"
        message = (
            "Animaciju trenutno nije moguće bezbedno prikazati. Pokušajte ponovo ili pojednostavite opis."
            if code == "invalid_animation_artifact"
            else "AI servis trenutno nije dostupan. Pokušajte ponovo."
        )
        raise HTTPException(status, detail={"code": code, "message": message}) from exc


@router.post("/render", response_class=FileResponse)
async def render_animation_mp4(
    payload: AnimationRequest,
    identity: RequestIdentity = Depends(get_authenticated_identity),
    provider: AnimationProvider = Depends(get_animation_provider),
) -> FileResponse:
    if not settings.animation_mp4_poc_enabled:
        raise HTTPException(404, detail="Animation MP4 PoC is not enabled.")
    if identity.user_id is None:
        raise HTTPException(401, detail="Authentication required.")
    try:
        plan = await provider.generate_plan(payload.prompt, payload.language)
        artifact = await asyncio.wait_for(
            run_in_threadpool(render_video, plan),
            timeout=settings.animation_render_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(504, detail={"code": "render_timeout", "message": "Renderovanje animacije je isteklo."}) from exc
    except CartoonRenderTimeout as exc:
        raise HTTPException(504, detail={"code": "render_timeout", "message": "Renderovanje animacije je isteklo."}) from exc
    except CartoonRenderError as exc:
        raise HTTPException(500, detail={"code": "animation_render_failed", "message": "MP4 animaciju trenutno nije moguće napraviti."}) from exc
    except AIProviderRateLimitError as exc:
        raise HTTPException(429, detail={"code": "provider_rate_limited", "message": "Servis za animacije je trenutno ograničen. Pokušajte ponovo kasnije."}) from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(504, detail={"code": "provider_timeout", "message": "Planiranje animacije je isteklo."}) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(503, detail={"code": "provider_unavailable", "message": "Servis za animacije je trenutno preopterećen."}) from exc
    except (AIAnimationPlanError, AIProviderResponseError) as exc:
        raise HTTPException(502, detail={"code": "invalid_animation_plan", "message": "Plan animacije nije moguće bezbedno prikazati."}) from exc
    except AIProviderConfigurationError as exc:
        raise HTTPException(503, detail={"code": "animation_failed", "message": "MP4 PoC trenutno nije pravilno konfigurisan."}) from exc
    except Exception as exc:
        raise HTTPException(500, detail={"code": "animation_render_failed", "message": "MP4 animaciju trenutno nije moguće napraviti."}) from exc
    return FileResponse(
        artifact.output_path,
        media_type="video/mp4",
        filename="askhype-cartoon-poc.mp4",
        headers={
            "X-AskHype-Animation-Frames": str(artifact.frame_count),
            "X-AskHype-Animation-Render-Seconds": f"{artifact.render_seconds:.3f}",
            "X-AskHype-Animation-Bytes": str(artifact.file_size),
            "X-AskHype-Animation-Resolution": "1280x720",
            "X-AskHype-Animation-FPS": "25",
            "X-AskHype-Animation-Model": provider.model,
        },
        background=BackgroundTask(cleanup_workspace, artifact.workspace),
    )


@router.post("/generate", response_model=AnimationResponse)
async def generate_animation(
    payload: AnimationRequest,
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: AnimationUsageRepository = Depends(get_animation_repository),
    provider: AnimationProvider = Depends(get_animation_provider),
) -> AnimationResponse:
    try:
        return await AnimationGenerationService(repository, provider).generate(payload, identity)
    except AnimationLimitReached as exc:
        raise HTTPException(429, detail={
            "code": "animation_daily_quota_reached",
            "message": f"Dostigli ste dnevni limit za animacije ({exc.limit}). Pokušajte ponovo sutra.",
            "used": exc.used, "limit": exc.limit, "remaining": 0, "reset_at": exc.reset_at.isoformat(),
        }) from exc
    except AIProviderRateLimitError as exc:
        raise HTTPException(429, detail={"code": "provider_rate_limited", "message": "Servis za animacije je trenutno ograničen. Pokušajte ponovo kasnije."}) from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(504, detail={"code": "provider_timeout", "message": "Generisanje animacije je isteklo. Pokušajte ponovo."}) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(503, detail={"code": "provider_unavailable", "message": "Servis za animacije je trenutno preopterećen. Pokušajte ponovo kasnije."}) from exc
    except (AIAnimationPlanError, AIProviderResponseError) as exc:
        raise HTTPException(502, detail={"code": "invalid_animation_plan", "message": "Plan animacije nije moguće bezbedno prikazati. Pokušajte sa drugačijim opisom."}) from exc
    except AIProviderConfigurationError as exc:
        raise HTTPException(503, detail={"code": "animation_failed", "message": "Generisanje animacije trenutno nije dostupno."}) from exc
    except PermissionError as exc:
        raise HTTPException(401, detail="Authentication required.") from exc
    except Exception as exc:
        raise HTTPException(500, detail={"code": "animation_failed", "message": "Animaciju trenutno nije moguće napraviti. Pokušajte ponovo."}) from exc
