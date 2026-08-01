from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_authenticated_identity,
    get_profile_repository,
)
from app.auth.identity import RequestIdentity
from app.repositories.profile_repository import ProfileRepository
from app.services.mock_subscription_service import (
    MockSubscriptionNotAllowed,
    MockSubscriptionNotFound,
    MockSubscriptionService,
    MockSubscriptionUnavailable,
    MockSubscriptionView,
)

router = APIRouter(tags=["mock-subscription"])


@router.get("/mock-subscription")
async def get_mock_subscription(
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: ProfileRepository = Depends(get_profile_repository),
) -> dict[str, object]:
    service = MockSubscriptionService(repository)
    view = await _safe_status(service, identity)
    return _status_payload(view)


@router.post("/mock-subscription/activate")
async def activate_mock_subscription(
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: ProfileRepository = Depends(get_profile_repository),
) -> dict[str, object]:
    service = MockSubscriptionService(repository)
    try:
        view = await service.activate(_user_id(identity))
    except MockSubscriptionNotAllowed as exc:
        raise _not_allowed() from exc
    except MockSubscriptionNotFound as exc:
        raise _not_found() from exc
    except MockSubscriptionUnavailable as exc:
        raise _unavailable() from exc
    return {
        "status": "active",
        "plan": view.plan,
        "is_mock": True,
        "message": "Demo Premium paket je aktiviran.",
    }


@router.post("/mock-subscription/deactivate")
async def deactivate_mock_subscription(
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: ProfileRepository = Depends(get_profile_repository),
) -> dict[str, object]:
    service = MockSubscriptionService(repository)
    try:
        view = await service.deactivate(_user_id(identity))
    except MockSubscriptionNotAllowed as exc:
        raise _not_allowed() from exc
    except MockSubscriptionNotFound as exc:
        raise _not_found() from exc
    except MockSubscriptionUnavailable as exc:
        raise _unavailable() from exc
    return {
        "status": "inactive",
        "plan": view.plan,
        "is_mock": True,
        "message": "Nalog je vraćen na besplatan paket.",
    }


async def _safe_status(
    service: MockSubscriptionService,
    identity: RequestIdentity,
) -> MockSubscriptionView:
    try:
        return await service.get_status(_user_id(identity))
    except MockSubscriptionNotFound as exc:
        raise _not_found() from exc
    except MockSubscriptionUnavailable as exc:
        raise _unavailable() from exc


def _status_payload(view: MockSubscriptionView) -> dict[str, object]:
    return {
        "enabled": view.enabled,
        "eligible": view.eligible,
        "plan": view.plan,
        "is_mock": True,
    }


def _user_id(identity: RequestIdentity):
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return identity.user_id


def _not_allowed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "mock_premium_not_allowed",
            "message": "Demo Premium aktivacija nije dostupna za ovaj nalog.",
        },
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Demo Premium trenutno nije dostupan. Pokušajte ponovo.",
    )
