from fastapi import Header

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
from app.services.usage_service import UsageService

_memory_usage_repository = InMemoryUsageRepository()


def get_usage_repository() -> UsageRepository:
    if settings.quota_enforcement_enabled:
        return SupabaseUsageRepository()
    return _memory_usage_repository


async def get_usage_service() -> UsageService:
    return UsageService(get_usage_repository())


async def get_request_identity(
    authorization: str | None = Header(default=None),
    x_anonymous_id: str | None = Header(default=None, alias="X-Anonymous-ID"),
) -> RequestIdentity:
    repository = get_usage_repository()
    if authorization:
        return await resolve_authenticated_identity(
            authorization,
            profile_plan_loader=repository,
        )
    return resolve_guest_identity(x_anonymous_id)
