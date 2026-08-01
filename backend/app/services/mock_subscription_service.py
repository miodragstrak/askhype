from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.core.config import settings
from app.repositories.profile_repository import MockSubscriptionStatus, ProfileRepository


class MockSubscriptionNotFound(RuntimeError):
    pass


class MockSubscriptionNotAllowed(RuntimeError):
    pass


class MockSubscriptionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MockSubscriptionView:
    enabled: bool
    eligible: bool
    plan: Literal["free", "premium"]
    is_mock: bool = True


class MockSubscriptionService:
    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    async def get_status(self, user_id: UUID) -> MockSubscriptionView:
        if not settings.mock_subscriptions_enabled:
            return MockSubscriptionView(enabled=False, eligible=False, plan="free")
        status = await self._load_status(user_id)
        return _view(status, enabled=True)

    async def activate(self, user_id: UUID) -> MockSubscriptionView:
        status = await self._eligible_status(user_id)
        if status.plan != "premium":
            status = await self._write_status(user_id, "premium")
            if not status.can_activate_mock_premium:
                raise MockSubscriptionNotAllowed("Mock premium activation is not allowed.")
            if status.plan != "premium":
                raise MockSubscriptionUnavailable("Mock subscription update unavailable.")
        return _view(status, enabled=True)

    async def deactivate(self, user_id: UUID) -> MockSubscriptionView:
        status = await self._eligible_status(user_id)
        if status.plan != "free":
            status = await self._write_status(user_id, "free")
            if not status.can_activate_mock_premium:
                raise MockSubscriptionNotAllowed("Mock premium activation is not allowed.")
            if status.plan != "free":
                raise MockSubscriptionUnavailable("Mock subscription update unavailable.")
        return _view(status, enabled=True)

    async def _eligible_status(self, user_id: UUID) -> MockSubscriptionStatus:
        if not settings.mock_subscriptions_enabled:
            raise MockSubscriptionNotFound("Mock subscriptions are disabled.")
        status = await self._load_status(user_id)
        if not status.can_activate_mock_premium:
            raise MockSubscriptionNotAllowed("Mock premium activation is not allowed.")
        return status

    async def _load_status(self, user_id: UUID) -> MockSubscriptionStatus:
        try:
            status = await self.repository.get_mock_subscription_status(user_id)
        except Exception as exc:
            raise MockSubscriptionUnavailable("Mock subscription status unavailable.") from exc
        if status is None:
            raise MockSubscriptionNotFound("Profile not found.")
        return status

    async def _write_status(self, user_id: UUID, plan: Literal["free", "premium"]) -> MockSubscriptionStatus:
        try:
            status = (
                await self.repository.activate_mock_premium(user_id)
                if plan == "premium"
                else await self.repository.deactivate_mock_premium(user_id)
            )
        except Exception as exc:
            raise MockSubscriptionUnavailable("Mock subscription update unavailable.") from exc
        if status is None:
            raise MockSubscriptionNotFound("Profile not found.")
        return status


def _view(status: MockSubscriptionStatus, *, enabled: bool) -> MockSubscriptionView:
    return MockSubscriptionView(
        enabled=enabled,
        eligible=status.can_activate_mock_premium,
        plan="premium" if status.plan == "premium" else "free",
    )
