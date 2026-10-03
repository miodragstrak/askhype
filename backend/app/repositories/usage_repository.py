from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
    reset_at: datetime | None = None


@dataclass(frozen=True)
class UsageStatus:
    used: int
    limit: int
    remaining: int
    reset_at: datetime | None = None


class UsageRepository(Protocol):
    async def get_plan_for_user(self, user_id: UUID) -> str: ...

    async def reserve_prompt_usage(
        self,
        *,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        limit: int,
        window_start: datetime,
        reserved_at: datetime,
        stale_before: datetime,
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
        window_start: datetime,
        stale_before: datetime,
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
        limit: int,
        window_start: datetime,
        reserved_at: datetime,
        stale_before: datetime,
        request_id: UUID,
    ) -> UsageReservation:
        response = self.client.rpc(
            "reserve_prompt_usage",
            {
                "p_user_id": str(user_id) if user_id else None,
                "p_anonymous_id_hash": anonymous_id_hash,
                "p_limit": limit,
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
            reset_at=_parse_datetime(data.get("reset_at")),
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
        window_start: datetime,
        stale_before: datetime,
        limit: int,
    ) -> UsageStatus:
        query = self.client.table("usage_events").select("id, created_at").gte(
            "created_at", window_start.isoformat()
        ).or_(f"status.eq.completed,and(status.eq.reserved,created_at.gte.{stale_before.isoformat()})")
        if user_id:
            query = query.eq("user_id", str(user_id))
        else:
            query = query.eq("anonymous_id_hash", anonymous_id_hash)
        response = query.execute()
        rows = getattr(response, "data", None) or []
        used = len(rows)
        created = [_parse_datetime(row.get("created_at")) for row in rows if isinstance(row, dict)]
        oldest = min((value for value in created if value is not None), default=None)
        reset_at = oldest + timedelta(hours=24) if oldest else None
        return UsageStatus(used=used, limit=limit, remaining=max(limit - used, 0), reset_at=reset_at)


def _first_row(value):
    if isinstance(value, list) and value:
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
        limit: int,
        window_start: datetime,
        reserved_at: datetime,
        stale_before: datetime,
        request_id: UUID,
    ) -> UsageReservation:
        self._expire_stale_reservations(stale_before)
        matching = self._matching_events(user_id, anonymous_id_hash, window_start, stale_before)
        used = len(matching)
        if used >= limit:
            return UsageReservation(
                allowed=False,
                usage_event_id=None,
                used=used,
                limit=limit,
                remaining=0,
                reset_at=self._reset_at(matching),
            )

        event_id = request_id
        self.events[event_id] = {
            "user_id": user_id,
            "anonymous_id_hash": anonymous_id_hash,
            "created_at": reserved_at,
            "status": "reserved",
        }
        used += 1
        return UsageReservation(
            allowed=True,
            usage_event_id=event_id,
            used=used,
            limit=limit,
            remaining=max(limit - used, 0),
            reset_at=self._reset_at(matching + [self.events[event_id]]),
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
        window_start: datetime,
        stale_before: datetime,
        limit: int,
    ) -> UsageStatus:
        self._expire_stale_reservations(stale_before)
        matching = self._matching_events(user_id, anonymous_id_hash, window_start, stale_before)
        used = len(matching)
        return UsageStatus(
            used=used,
            limit=limit,
            remaining=max(limit - used, 0),
            reset_at=self._reset_at(matching),
        )

    def _matching_events(
        self,
        user_id: UUID | None,
        anonymous_id_hash: str | None,
        window_start: datetime,
        stale_before: datetime,
    ) -> list[dict[str, object]]:
        return [
            event
            for event in self.events.values()
            if isinstance(event.get("created_at"), datetime)
            and event["created_at"] >= window_start
            and (event.get("status") == "completed" or (event.get("status") == "reserved" and event["created_at"] >= stale_before))
            and (
                event.get("user_id") == user_id
                if user_id is not None
                else event.get("anonymous_id_hash") == anonymous_id_hash
            )
        ]

    def _expire_stale_reservations(self, stale_before: datetime) -> None:
        for event in self.events.values():
            created_at = event.get("created_at")
            if event.get("status") == "reserved" and isinstance(created_at, datetime) and created_at < stale_before:
                event.update({"status": "failed", "failure_code": "stale_reservation"})

    @staticmethod
    def _reset_at(events: list[dict[str, object]]) -> datetime | None:
        created = [event["created_at"] for event in events if isinstance(event.get("created_at"), datetime)]
        return min(created) + timedelta(hours=24) if created else None
