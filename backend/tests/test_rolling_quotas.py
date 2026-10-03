import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.auth.identity import RequestIdentity, resolve_guest_identity
from app.core.config import settings
from app.repositories.usage_repository import InMemoryUsageRepository
from app.services.usage_service import PromptLimitReached, UsageService

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def _authenticated(plan: str) -> RequestIdentity:
    return RequestIdentity(
        kind="authenticated",
        user_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        anonymous_id_hash=None,
        plan=plan,
        email="quota@example.com",
    )


def _complete(service: UsageService, identity: RequestIdentity, count: int) -> None:
    for _ in range(count):
        reservation = asyncio.run(service.reserve(identity))
        asyncio.run(
            service.finalize(
                reservation.usage_event_id,
                status="completed",
                provider="mock",
                conversation_id="conversation",
                failure_code=None,
            )
        )


@pytest.mark.parametrize(("plan", "allowed"), [("free", 10), ("premium", 200)])
def test_registered_rolling_limits_allow_exact_limit_then_reject(plan: str, allowed: int) -> None:
    service = UsageService(InMemoryUsageRepository(), clock=lambda: NOW)
    identity = _authenticated(plan)

    _complete(service, identity, allowed)

    snapshot = asyncio.run(service.get_status(identity))
    assert snapshot.used == allowed
    assert snapshot.remaining == 0
    with pytest.raises(PromptLimitReached):
        asyncio.run(service.reserve(identity))


def test_event_older_than_24_hours_no_longer_counts() -> None:
    repository = InMemoryUsageRepository()
    identity = _authenticated("free")
    repository.events[uuid4()] = {
        "user_id": identity.user_id,
        "anonymous_id_hash": None,
        "created_at": NOW - timedelta(hours=24, microseconds=1),
        "status": "completed",
    }
    service = UsageService(repository, clock=lambda: NOW)

    assert asyncio.run(service.get_status(identity)).used == 0


def test_event_inside_24_hour_window_counts() -> None:
    repository = InMemoryUsageRepository()
    identity = _authenticated("free")
    repository.events[uuid4()] = {
        "user_id": identity.user_id,
        "anonymous_id_hash": None,
        "created_at": NOW - timedelta(hours=23, minutes=59),
        "status": "completed",
    }
    service = UsageService(repository, clock=lambda: NOW)

    snapshot = asyncio.run(service.get_status(identity))
    assert snapshot.used == 1
    assert snapshot.reset_at == NOW + timedelta(minutes=1)


def test_stale_reservation_is_failed_and_releases_quota() -> None:
    repository = InMemoryUsageRepository()
    identity = _authenticated("free")
    event_id = uuid4()
    repository.events[event_id] = {
        "user_id": identity.user_id,
        "anonymous_id_hash": None,
        "created_at": NOW - timedelta(minutes=11),
        "status": "reserved",
    }
    service = UsageService(repository, clock=lambda: NOW)

    assert asyncio.run(service.get_status(identity)).used == 0
    assert repository.events[event_id]["status"] == "failed"
    assert repository.events[event_id]["failure_code"] == "stale_reservation"


def test_anonymous_limit_remains_server_configurable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anonymous_prompt_limit", 2)
    identity = resolve_guest_identity("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    service = UsageService(InMemoryUsageRepository(), clock=lambda: NOW)

    _complete(service, identity, 2)
    with pytest.raises(PromptLimitReached):
        asyncio.run(service.reserve(identity))


def test_quota_disabled_mode_uses_process_local_repository() -> None:
    from app.api import dependencies

    settings.quota_enforcement_enabled = False
    assert dependencies.get_usage_repository() is dependencies._memory_usage_repository
