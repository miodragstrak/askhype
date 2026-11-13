from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.clients.supabase import get_supabase_admin_client


class AnimationLimitReached(RuntimeError):
    def __init__(self, used: int, limit: int, reset_at: datetime) -> None:
        self.used, self.limit, self.reset_at = used, limit, reset_at


class AnimationUsageRepository(Protocol):
    async def reserve(self, *, event_id: UUID, user_id: UUID, limit: int) -> dict[str, Any]: ...
    async def finalize(self, event_id: UUID, *, status: str, failure_category: str | None = None) -> None: ...


class SupabaseAnimationUsageRepository:
    def __init__(self, client=None) -> None:
        self.client = client or get_supabase_admin_client()

    async def reserve(self, *, event_id: UUID, user_id: UUID, limit: int) -> dict[str, Any]:
        response = self.client.rpc("reserve_animation_usage", {
            "p_event_id": str(event_id), "p_user_id": str(user_id), "p_limit": limit,
        }).execute()
        row = _row(getattr(response, "data", None))
        if not row.get("allowed"):
            raise AnimationLimitReached(int(row["used"]), int(row["limit"]), _datetime(row["reset_at"]))
        return _quota(row)

    async def finalize(self, event_id: UUID, *, status: str, failure_category: str | None = None) -> None:
        self.client.rpc("finalize_animation_usage", {
            "p_event_id": str(event_id), "p_status": status, "p_failure_category": failure_category,
        }).execute()


class InMemoryAnimationUsageRepository:
    def __init__(self) -> None:
        self.events: dict[UUID, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, *, event_id: UUID, user_id: UUID, limit: int) -> dict[str, Any]:
        async with self._lock:
            now = datetime.now(UTC)
            reset_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            used = sum(
                event["status"] in {"reserved", "completed"}
                and event["user_id"] == user_id
                and event["created_at"].date() == now.date()
                for event in self.events.values()
            )
            if used >= limit:
                raise AnimationLimitReached(used, limit, reset_at)
            self.events[event_id] = {
                "id": event_id, "user_id": user_id, "status": "reserved", "created_at": now,
                "failure_category": None,
            }
            return {"used": used + 1, "limit": limit, "remaining": max(limit - used - 1, 0), "reset_at": reset_at}

    async def finalize(self, event_id: UUID, *, status: str, failure_category: str | None = None) -> None:
        async with self._lock:
            event = self.events[event_id]
            event.update(status=status, failure_category=failure_category)


def _row(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value:
        return value[0]
    return value if isinstance(value, dict) else {}


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _quota(row: dict[str, Any]) -> dict[str, Any]:
    used, limit = int(row["used"]), int(row["limit"])
    return {"used": used, "limit": limit, "remaining": max(limit - used, 0), "reset_at": _datetime(row["reset_at"])}
