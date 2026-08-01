from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_request_identity, get_usage_service
from app.auth.identity import RequestIdentity
from app.services.usage_service import UsageService, UsageServiceUnavailable

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def usage(
    identity: RequestIdentity = Depends(get_request_identity),
    usage_service: UsageService = Depends(get_usage_service),
) -> dict[str, object]:
    try:
        snapshot = await usage_service.get_status(identity)
    except UsageServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AskHype kvote trenutno nisu dostupne. Pokušajte ponovo.",
        ) from exc
    return {
        "identity": snapshot.identity,
        "plan": snapshot.plan,
        "used": snapshot.used,
        "limit": snapshot.limit,
        "remaining": snapshot.remaining,
        "reset_at": snapshot.reset_at.isoformat() if snapshot.reset_at else None,
    }
