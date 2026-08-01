import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.auth.identity import (
    hash_anonymous_id,
    resolve_authenticated_identity,
    resolve_guest_identity,
)
from app.core.config import settings
from app.repositories.usage_repository import InMemoryUsageRepository
from app.services.usage_service import (
    PromptLimitReached,
    UsageService,
    quota_payload,
    usage_window,
)


class FakeVerifier:
    def __init__(self, claims=None, exc: Exception | None = None) -> None:
        self.claims = claims
        self.exc = exc

    async def verify_claims(self, token: str):
        if self.exc:
            raise self.exc
        return self.claims


class FakePlanLoader:
    def __init__(self, plan: str) -> None:
        self.plan = plan

    async def get_plan_for_user(self, user_id: UUID) -> str:
        return self.plan


def test_valid_authenticated_identity_loads_profile_plan() -> None:
    user_id = UUID("33333333-3333-4333-8333-333333333333")

    identity = asyncio.run(
        resolve_authenticated_identity(
            "Bearer good-token",
            verifier=FakeVerifier({"sub": str(user_id), "email": "demo@example.com"}),
            profile_plan_loader=FakePlanLoader("premium"),
        )
    )

    assert identity.kind == "authenticated"
    assert identity.user_id == user_id
    assert identity.plan == "premium"
    assert identity.email == "demo@example.com"
    assert identity.anonymous_id_hash is None


def test_invalid_token_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            resolve_authenticated_identity(
                "Bearer bad-token",
                verifier=FakeVerifier(exc=ValueError("expired")),
            )
        )

    assert exc_info.value.status_code == 401


def test_missing_and_malformed_guest_identity() -> None:
    with pytest.raises(HTTPException) as missing:
        resolve_guest_identity(None)
    with pytest.raises(HTTPException) as malformed:
        resolve_guest_identity("not-a-uuid")

    assert missing.value.status_code == 400
    assert malformed.value.status_code == 400


def test_guest_hash_is_stable_and_not_raw_uuid() -> None:
    raw_id = "44444444-4444-4444-8444-444444444444"
    first = hash_anonymous_id(raw_id, "pepper")
    second = hash_anonymous_id(raw_id, "pepper")

    assert first == second
    assert first.startswith("guest_")
    assert raw_id not in first


def test_free_plan_cannot_be_supplied_from_client_and_premium_only_from_profile() -> None:
    user_id = UUID("55555555-5555-4555-8555-555555555555")
    identity = asyncio.run(
        resolve_authenticated_identity(
            "Bearer token",
            verifier=FakeVerifier({"sub": str(user_id), "app_metadata": {"plan": "premium"}}),
            profile_plan_loader=FakePlanLoader("free"),
        )
    )
    premium_identity = asyncio.run(
        resolve_authenticated_identity(
            "Bearer token",
            verifier=FakeVerifier({"sub": str(user_id)}),
            profile_plan_loader=FakePlanLoader("premium"),
        )
    )

    assert identity.plan == "free"
    assert premium_identity.plan == "premium"


def test_quota_periods_are_utc() -> None:
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    guest = usage_window("guest", now)
    free = usage_window("free", now)
    premium = usage_window("premium", now)

    assert guest.period_start == datetime(2020, 1, 1, tzinfo=UTC)
    assert guest.reset_at is None
    assert free.period_start == datetime(2026, 8, 1, tzinfo=UTC)
    assert free.reset_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert premium.period_start == datetime(2026, 8, 1, tzinfo=UTC)


def test_quota_allowed_and_exhausted_flow() -> None:
    settings.anonymous_prompt_limit = 1
    identity = resolve_guest_identity("66666666-6666-4666-8666-666666666666")
    service = UsageService(InMemoryUsageRepository())

    reserved = asyncio.run(service.reserve(identity))
    asyncio.run(
        service.finalize(
            reserved.usage_event_id,
            status="completed",
            provider="mock",
            conversation_id="conv",
            failure_code=None,
        )
    )

    with pytest.raises(PromptLimitReached) as exc_info:
        asyncio.run(service.reserve(identity))

    payload = quota_payload(exc_info.value.snapshot)
    assert payload["code"] == "prompt_limit_reached"
    assert payload["identity"] == "guest"
    assert payload["remaining"] == 0
    assert payload["actions"] == ["sign_up", "sign_in", "view_premium"]
    settings.anonymous_prompt_limit = 3
