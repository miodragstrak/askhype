from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import (
    get_animation_provider, get_animation_repository, get_authenticated_identity,
)
from app.auth.identity import RequestIdentity
from app.providers.animation import AnimationProvider
from app.providers.exceptions import (
    AIAnimationPlanError, AIProviderConfigurationError, AIProviderRateLimitError,
    AIProviderResponseError, AIProviderTimeoutError, AIProviderUnavailableError,
)
from app.repositories.animation_repository import AnimationLimitReached, AnimationUsageRepository
from app.schemas.animations import AnimationRequest, AnimationResponse
from app.services.animation_generation import AnimationGenerationService

router = APIRouter(prefix="/animations", tags=["animations"])


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
