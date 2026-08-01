from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.repositories.usage_repository import UsageRepository, UsageReservation, UsageStatus


@dataclass(frozen=True)
class UsageWindow:
    period_start: datetime
    reset_at: datetime | None
    limit: int


@dataclass(frozen=True)
class UsageSnapshot:
    identity: Literal["guest", "authenticated"]
    plan: str
    used: int
    limit: int
    remaining: int
    reset_at: datetime | None


@dataclass(frozen=True)
class ReservedUsage:
    request_id: UUID
    usage_event_id: UUID
    snapshot: UsageSnapshot


class PromptLimitReached(RuntimeError):
    def __init__(self, snapshot: UsageSnapshot) -> None:
        self.snapshot = snapshot
        super().__init__("Prompt limit reached.")


class UsageServiceUnavailable(RuntimeError):
    pass


class UsageService:
    def __init__(self, repository: UsageRepository) -> None:
        self.repository = repository

    async def reserve(self, identity: RequestIdentity) -> ReservedUsage:
        request_id = uuid4()
        window = usage_window(identity.plan)
        try:
            reservation = await self.repository.reserve_prompt_usage(
                user_id=identity.user_id,
                anonymous_id_hash=identity.anonymous_id_hash,
                plan=identity.plan,
                limit=window.limit,
                period_start=window.period_start,
                request_id=request_id,
            )
        except Exception as exc:
            raise UsageServiceUnavailable("Usage reservation unavailable.") from exc

        snapshot = _snapshot(identity, reservation, window)
        if not reservation.allowed or reservation.usage_event_id is None:
            raise PromptLimitReached(snapshot)
        return ReservedUsage(request_id=request_id, usage_event_id=reservation.usage_event_id, snapshot=snapshot)

    async def finalize(
        self,
        usage_event_id: UUID,
        *,
        status: str,
        provider: str | None,
        conversation_id: str | None,
        failure_code: str | None,
    ) -> None:
        try:
            await self.repository.finalize_prompt_usage(
                usage_event_id=usage_event_id,
                status=status,
                provider=provider,
                conversation_id=conversation_id,
                failure_code=failure_code,
            )
        except Exception:
            return

    async def get_status(self, identity: RequestIdentity) -> UsageSnapshot:
        window = usage_window(identity.plan)
        try:
            status = await self.repository.get_usage_status(
                user_id=identity.user_id,
                anonymous_id_hash=identity.anonymous_id_hash,
                period_start=window.period_start,
                limit=window.limit,
            )
        except Exception as exc:
            raise UsageServiceUnavailable("Usage status unavailable.") from exc
        return _snapshot(identity, status, window)


def usage_window(plan: str, now: datetime | None = None) -> UsageWindow:
    now = now or datetime.now(UTC)
    if plan == "guest":
        return UsageWindow(
            period_start=datetime(2020, 1, 1, tzinfo=UTC),
            reset_at=None,
            limit=settings.anonymous_prompt_limit,
        )

    period_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    next_month = datetime(now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1, tzinfo=UTC)
    limit = settings.premium_monthly_prompt_limit if plan == "premium" else settings.free_monthly_prompt_limit
    return UsageWindow(period_start=period_start, reset_at=next_month, limit=limit)


def quota_payload(snapshot: UsageSnapshot) -> dict[str, object]:
    if snapshot.plan == "guest":
        actions = ["sign_up", "sign_in", "view_premium"]
    elif snapshot.plan == "premium":
        actions = ["contact_support"]
    else:
        actions = ["view_premium"]
    return {
        "code": "prompt_limit_reached",
        "message": "Iskoristio si dostupna AskHype pitanja.",
        "identity": snapshot.identity,
        "plan": snapshot.plan,
        "used": snapshot.used,
        "limit": snapshot.limit,
        "remaining": max(snapshot.remaining, 0),
        "reset_at": snapshot.reset_at.isoformat() if snapshot.reset_at else None,
        "actions": actions,
    }


def usage_headers(snapshot: UsageSnapshot) -> dict[str, str]:
    return {
        "X-AskHype-Plan": snapshot.plan,
        "X-AskHype-Usage-Used": str(snapshot.used),
        "X-AskHype-Usage-Limit": str(snapshot.limit),
        "X-AskHype-Usage-Remaining": str(max(snapshot.remaining, 0)),
    }


def _snapshot(identity: RequestIdentity, usage: UsageReservation | UsageStatus, window: UsageWindow) -> UsageSnapshot:
    return UsageSnapshot(
        identity=identity.kind,
        plan=identity.plan,
        used=usage.used,
        limit=usage.limit,
        remaining=max(usage.remaining, 0),
        reset_at=window.reset_at,
    )
