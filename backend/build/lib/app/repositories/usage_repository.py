from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.clients.supabase import get_supabase_admin_client


@dataclass(frozen=True)
class UsageReservation:
    allowed: bool
    usage_event_id: UUID | None
    used: int
    limit: int
    remaining: int


@dataclass(frozen=True)
class UsageStatus:
    used: int
    limit: int
    remaining: int


class UsageRepository(Protocol):
    async def get_plan_for_user(self, user_id: UUID) -> str: ...

    async def reserve_prompt_usage(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        plan: str,
        limit: int,
        period_start: datetime,
        request_id: UUID,
    ) -> UsageReservation: ...

    async def finalize_prompt_usage(
        self,
        *,
        usage_event_id: UUID,
        status: str,
        provider: str | None,
        conversation_id: str | None,
        failure_code: str | None,
    ) -> None: ...

    async def get_usage_status(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        period_start: datetime,
        limit: int,
    ) -> UsageStatus: ...


class SupabaseUsageRepository:
    def __init__(self, client=None) -> None:
        self.client = client or get_supabase_admin_client()

    async def get_plan_for_user(self, user_id: UUID) -> str:
        response = (
            self.client.table("profiles")
            .select("plan")
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
        data = getattr(response, "data", None) or {}
        plan = data.get("plan") if isinstance(data, dict) else None
        return "premium" if plan == "premium" else "free"

    async def reserve_prompt_usage(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        plan: str,
        limit: int,
        period_start: datetime,
        request_id: UUID,
    ) -> UsageReservation:
        response = self.client.rpc(
            "reserve_prompt_usage",
            {
                "p_user_id": str(user_id) if user_id else None,
                "p_anonymous_id": anonymous_id_hash,
                "p_plan": plan,
                "p_limit": limit,
                "p_period_start": period_start.isoformat(),
                "p_request_id": str(request_id),
            },
        ).execute()
        data = _first_row(getattr(response, "data", None))
        return UsageReservation(
            allowed=bool(data.get("allowed")),
            usage_event_id=UUID(str(data["usage_event_id"])) if data.get("usage_event_id") else None,
            used=int(data.get("used", 0)),
            limit=int(data.get("limit", limit)),
            remaining=max(int(data.get("remaining", 0)), 0),
        )

    async def finalize_prompt_usage(
        self,
        *,
        usage_event_id: UUID,
        status: str,
        provider: str | None,
        conversation_id: str | None,
        failure_code: str | None,
    ) -> None:
        self.client.rpc(
            "finalize_prompt_usage",
            {
                "p_usage_event_id": str(usage_event_id),
                "p_status": status,
                "p_provider": provider,
                "p_conversation_id": conversation_id,
                "p_failure_code": failure_code,
            },
        ).execute()

    async def get_usage_status(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        period_start: datetime,
        limit: int,
    ) -> UsageStatus:
        query = self.client.table("usage_events").select("id", count="exact").gte(
            "period_start",
            period_start.isoformat(),
        ).in_("status", ["reserved", "completed"])
        if user_id:
            query = query.eq("user_id", str(user_id))
        else:
            query = query.eq("anonymous_id", anonymous_id_hash)
        response = query.execute()
        used = int(getattr(response, "count", 0) or 0)
        return UsageStatus(used=used, limit=limit, remaining=max(limit - used, 0))


def _first_row(value):
    if isinstance(value, list) and value:
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


class InMemoryUsageRepository:
    def __init__(self) -> None:
        self.plans: dict[UUID, str] = {}
        self.events: dict[UUID, dict[str, object]] = {}

    async def get_plan_for_user(self, user_id: UUID) -> str:
        return "premium" if self.plans.get(user_id) == "premium" else "free"

    async def reserve_prompt_usage(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        plan: str,
        limit: int,
        period_start: datetime,
        request_id: UUID,
    ) -> UsageReservation:
        used = self._count(user_id, anonymous_id_hash, period_start)
        if used >= limit:
            return UsageReservation(
                allowed=False,
                usage_event_id=None,
                used=used,
                limit=limit,
                remaining=0,
            )

        event_id = request_id
        self.events[event_id] = {
            "user_id": user_id,
            "anonymous_id_hash": anonymous_id_hash,
            "period_start": period_start,
            "status": "reserved",
            "plan": plan,
        }
        used += 1
        return UsageReservation(
            allowed=True,
            usage_event_id=event_id,
            used=used,
            limit=limit,
            remaining=max(limit - used, 0),
        )

    async def finalize_prompt_usage(
        self,
        *,
        usage_event_id: UUID,
        status: str,
        provider: str | None,
        conversation_id: str | None,
        failure_code: str | None,
    ) -> None:
        event = self.events.get(usage_event_id)
        if event is None:
            return
        if status == "failed":
            self.events.pop(usage_event_id, None)
            return
        event.update(
            {
                "status": status,
                "provider": provider,
                "conversation_id": conversation_id,
                "failure_code": failure_code,
            }
        )

    async def get_usage_status(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        period_start: datetime,
        limit: int,
    ) -> UsageStatus:
        used = self._count(user_id, anonymous_id_hash, period_start)
        return UsageStatus(used=used, limit=limit, remaining=max(limit - used, 0))

    def _count(
        self,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        period_start: datetime,
    ) -> int:
        return sum(
            1
            for event in self.events.values()
            if event.get("status") in {"reserved", "completed"}
            and event.get("period_start") == period_start
            and (
                event.get("user_id") == user_id
                if user_id is not None
                else event.get("anonymous_id_hash") == anonymous_id_hash
            )
        )
