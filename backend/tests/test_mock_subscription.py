import asyncio
from uuid import UUID

import httpx
import pytest

from app.api import dependencies
from app.auth.identity import RequestIdentity
from app.main import app

ELIGIBLE_USER = UUID("88888888-8888-4888-8888-888888888888")
OTHER_USER = UUID("99999999-9999-4999-8999-999999999999")


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _identity(user_id: UUID) -> RequestIdentity:
    return RequestIdentity(
        kind="authenticated",
        user_id=user_id,
        anonymous_id_hash=None,
        plan="free",
        email="demo@example.com",
    )


def _override_identity(user_id: UUID) -> None:
    async def authenticated_identity() -> RequestIdentity:
        return _identity(user_id)

    async def request_identity() -> RequestIdentity:
        plan = await dependencies._memory_profile_repository.get_plan_for_user(user_id)
        identity = _identity(user_id)
        return RequestIdentity(
            kind=identity.kind,
            user_id=identity.user_id,
            anonymous_id_hash=identity.anonymous_id_hash,
            plan="premium" if plan == "premium" else "free",
            email=identity.email,
        )

    app.dependency_overrides[dependencies.get_authenticated_identity] = authenticated_identity
    app.dependency_overrides[dependencies.get_request_identity] = request_identity


def _allow_mock_premium(user_id: UUID, *, plan: str = "free") -> None:
    dependencies._memory_profile_repository.mock_premium_allowed.add(user_id)
    dependencies._memory_profile_repository.plans[user_id] = plan


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.get(path, headers=headers)


async def _post(path: str, json: dict[str, object] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.post(path, json=json)


def test_guest_cannot_access_mock_subscription_endpoints() -> None:
    response = asyncio.run(_get("/api/mock-subscription"))

    assert response.status_code == 401


def test_invalid_token_returns_401_without_supabase_call() -> None:
    response = asyncio.run(_get("/api/mock-subscription", headers={"Authorization": "Bearer bad"}))

    assert response.status_code == 401


def test_feature_disabled_returns_safe_status(monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.mock_subscriptions_enabled", False)
    _override_identity(ELIGIBLE_USER)
    _allow_mock_premium(ELIGIBLE_USER)

    response = asyncio.run(_get("/api/mock-subscription"))

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "eligible": False,
        "plan": "free",
        "is_mock": True,
    }


def test_eligible_and_non_eligible_status() -> None:
    _override_identity(ELIGIBLE_USER)
    _allow_mock_premium(ELIGIBLE_USER)
    eligible = asyncio.run(_get("/api/mock-subscription"))

    app.dependency_overrides.clear()
    _override_identity(OTHER_USER)
    ordinary = asyncio.run(_get("/api/mock-subscription"))

    assert eligible.json()["eligible"] is True
    assert eligible.json()["plan"] == "free"
    assert ordinary.json()["eligible"] is False


def test_eligible_free_user_can_activate_and_activation_is_idempotent() -> None:
    _override_identity(ELIGIBLE_USER)
    _allow_mock_premium(ELIGIBLE_USER)

    first = asyncio.run(_post("/api/mock-subscription/activate"))
    second = asyncio.run(_post("/api/mock-subscription/activate"))

    assert first.status_code == 200
    assert first.json()["plan"] == "premium"
    assert first.json()["message"] == "Demo Premium paket je aktiviran."
    assert second.status_code == 200
    assert dependencies._memory_profile_repository.plans[ELIGIBLE_USER] == "premium"


def test_non_eligible_user_receives_403() -> None:
    _override_identity(OTHER_USER)

    response = asyncio.run(_post("/api/mock-subscription/activate"))

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "mock_premium_not_allowed"
    assert "database" not in detail["message"].casefold()


def test_activation_changes_only_current_user_and_does_not_modify_eligibility() -> None:
    _override_identity(ELIGIBLE_USER)
    _allow_mock_premium(ELIGIBLE_USER)
    _allow_mock_premium(OTHER_USER)

    response = asyncio.run(
        _post(
            "/api/mock-subscription/activate",
            json={"user_id": str(OTHER_USER), "plan": "premium", "can_activate_mock_premium": False},
        )
    )

    assert response.status_code == 200
    assert dependencies._memory_profile_repository.plans[ELIGIBLE_USER] == "premium"
    assert dependencies._memory_profile_repository.plans[OTHER_USER] == "free"
    assert ELIGIBLE_USER in dependencies._memory_profile_repository.mock_premium_allowed


def test_deactivation_changes_only_current_user() -> None:
    _override_identity(ELIGIBLE_USER)
    _allow_mock_premium(ELIGIBLE_USER, plan="premium")
    _allow_mock_premium(OTHER_USER, plan="premium")

    response = asyncio.run(_post("/api/mock-subscription/deactivate", json={"user_id": str(OTHER_USER)}))

    assert response.status_code == 200
    assert response.json()["plan"] == "free"
    assert dependencies._memory_profile_repository.plans[ELIGIBLE_USER] == "free"
    assert dependencies._memory_profile_repository.plans[OTHER_USER] == "premium"


def test_usage_endpoint_reflects_plan_after_activation_and_deactivation() -> None:
    _override_identity(ELIGIBLE_USER)
    _allow_mock_premium(ELIGIBLE_USER)

    activated = asyncio.run(_post("/api/mock-subscription/activate"))
    premium_usage = asyncio.run(_get("/api/usage"))
    deactivated = asyncio.run(_post("/api/mock-subscription/deactivate"))
    free_usage = asyncio.run(_get("/api/usage"))

    assert activated.status_code == 200
    assert premium_usage.json()["plan"] == "premium"
    assert premium_usage.json()["limit"] == 200
    assert deactivated.status_code == 200
    assert free_usage.json()["plan"] == "free"
    assert free_usage.json()["limit"] == 10


def test_missing_profile_returns_safe_404() -> None:
    _override_identity(ELIGIBLE_USER)
    dependencies._memory_profile_repository.missing_profiles.add(ELIGIBLE_USER)

    response = asyncio.run(_get("/api/mock-subscription"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


def test_repository_failure_returns_safe_server_error() -> None:
    _override_identity(ELIGIBLE_USER)
    dependencies._memory_profile_repository.failures_enabled = True

    response = asyncio.run(_get("/api/mock-subscription"))

    assert response.status_code == 503
    assert "secret token" not in response.text
    assert "database exploded" not in response.text
