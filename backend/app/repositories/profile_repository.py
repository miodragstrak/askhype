from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.clients.supabase import get_supabase_admin_client


@dataclass(frozen=True)
class MockSubscriptionStatus:
    plan: str
    can_activate_mock_premium: bool


class ProfileRepository(Protocol):
    async def get_plan_for_user(self, user_id: UUID) -> str: ...

    async def get_mock_subscription_status(self, user_id: UUID) -> MockSubscriptionStatus | None: ...

    async def activate_mock_premium(self, user_id: UUID) -> MockSubscriptionStatus | None: ...

    async def deactivate_mock_premium(self, user_id: UUID) -> MockSubscriptionStatus | None: ...


class SupabaseProfileRepository:
    def __init__(self, client=None) -> None:
        self.client = client or get_supabase_admin_client()

    async def get_plan_for_user(self, user_id: UUID) -> str:
        status = await self.get_mock_subscription_status(user_id)
        return "premium" if status and status.plan == "premium" else "free"

    async def get_mock_subscription_status(self, user_id: UUID) -> MockSubscriptionStatus | None:
        response = (
            self.client.table("profiles")
            .select("plan, can_activate_mock_premium")
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
        return _status_from_row(getattr(response, "data", None))

    async def activate_mock_premium(self, user_id: UUID) -> MockSubscriptionStatus | None:
        return await self._set_plan(user_id, "premium")

    async def deactivate_mock_premium(self, user_id: UUID) -> MockSubscriptionStatus | None:
        return await self._set_plan(user_id, "free")

    async def _set_plan(self, user_id: UUID, plan: str) -> MockSubscriptionStatus | None:
        response = (
            self.client.table("profiles")
            .update({"plan": plan})
            .eq("user_id", str(user_id))
            .eq("can_activate_mock_premium", True)
            .execute()
        )
        data = getattr(response, "data", None)
        if isinstance(data, list):
            if data:
                return _status_from_row(data[0])
            return await self.get_mock_subscription_status(user_id)
        return _status_from_row(data)


def _status_from_row(row: object) -> MockSubscriptionStatus | None:
    if not isinstance(row, dict):
        return None
    plan = "premium" if row.get("plan") == "premium" else "free"
    return MockSubscriptionStatus(
        plan=plan,
        can_activate_mock_premium=bool(row.get("can_activate_mock_premium")),
    )


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.plans: dict[UUID, str] = {}
        self.mock_premium_allowed: set[UUID] = set()
        self.missing_profiles: set[UUID] = set()
        self.failures_enabled = False

    async def get_plan_for_user(self, user_id: UUID) -> str:
        if user_id in self.missing_profiles:
            return "free"
        return "premium" if self.plans.get(user_id) == "premium" else "free"

    async def get_mock_subscription_status(self, user_id: UUID) -> MockSubscriptionStatus | None:
        self._raise_if_needed()
        if user_id in self.missing_profiles:
            return None
        return MockSubscriptionStatus(
            plan="premium" if self.plans.get(user_id) == "premium" else "free",
            can_activate_mock_premium=user_id in self.mock_premium_allowed,
        )

    async def activate_mock_premium(self, user_id: UUID) -> MockSubscriptionStatus | None:
        self._raise_if_needed()
        if user_id in self.missing_profiles:
            return None
        self.plans[user_id] = "premium"
        return await self.get_mock_subscription_status(user_id)

    async def deactivate_mock_premium(self, user_id: UUID) -> MockSubscriptionStatus | None:
        self._raise_if_needed()
        if user_id in self.missing_profiles:
            return None
        self.plans[user_id] = "free"
        return await self.get_mock_subscription_status(user_id)

    def clear(self) -> None:
        self.plans.clear()
        self.mock_premium_allowed.clear()
        self.missing_profiles.clear()
        self.failures_enabled = False

    def _raise_if_needed(self) -> None:
        if self.failures_enabled:
            raise RuntimeError("database exploded with secret token")
