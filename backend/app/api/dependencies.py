from fastapi import Header, HTTPException, status

from app.auth.identity import (
    RequestIdentity,
    resolve_authenticated_identity,
    resolve_guest_identity,
)
from app.core.config import settings
from app.repositories.usage_repository import (
    InMemoryUsageRepository,
    SupabaseUsageRepository,
    UsageRepository,
)
from app.repositories.profile_repository import (
    InMemoryProfileRepository,
    ProfileRepository,
    SupabaseProfileRepository,
)
from app.services.usage_service import UsageService

_memory_usage_repository = InMemoryUsageRepository()
_memory_profile_repository = InMemoryProfileRepository()


def get_usage_repository() -> UsageRepository:
    if settings.quota_enforcement_enabled:
        return SupabaseUsageRepository()
    return _memory_usage_repository


async def get_usage_service() -> UsageService:
    return UsageService(get_usage_repository())


async def get_profile_repository() -> ProfileRepository:
    if settings.quota_enforcement_enabled:
        return SupabaseProfileRepository()
    return _memory_profile_repository


async def get_request_identity(
    authorization: str | None = Header(default=None),
    x_anonymous_id: str | None = Header(default=None, alias="X-Anonymous-ID"),
) -> RequestIdentity:
    profile_repository = await get_profile_repository()
    if authorization:
        return await resolve_authenticated_identity(
            authorization,
            profile_plan_loader=profile_repository,
        )
    return resolve_guest_identity(x_anonymous_id)


async def get_authenticated_identity(
    authorization: str | None = Header(default=None),
) -> RequestIdentity:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    profile_repository = await get_profile_repository()
    return await resolve_authenticated_identity(
        authorization,
        profile_plan_loader=profile_repository,
    )
