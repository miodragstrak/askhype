import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "ai_provider": "gemini",
        "quota_enforcement_enabled": True,
        "supabase_url": "https://example.supabase.co",
        "supabase_secret_key": "server-secret",
        "anonymous_id_pepper": "identity-pepper",
        "gemini_api_key": "gemini-secret",
        "frontend_origin": "https://askhype.example",
        "frontend_origins": None,
        "mock_subscriptions_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_and_staging_do_not_require_production_secrets() -> None:
    development = Settings(
        _env_file=None,
        app_env="development",
        frontend_origin=None,
        frontend_origins=None,
        gemini_api_key=None,
        supabase_url=None,
        supabase_secret_key=None,
        anonymous_id_pepper=None,
    )
    staging = Settings(
        _env_file=None,
        app_env="staging",
        frontend_origin="https://staging.askhype.example/",
        gemini_api_key=None,
        supabase_url=None,
        supabase_secret_key=None,
        anonymous_id_pepper=None,
    )

    assert development.ai_provider == "mock"
    assert development.allowed_frontend_origins == ["http://localhost:5173"]
    assert development.anonymous_prompt_limit == 5
    assert staging.allowed_frontend_origins == ["https://staging.askhype.example"]


def test_frontend_origin_allowlist_combines_legacy_and_csv_values() -> None:
    app_settings = Settings(
        _env_file=None,
        frontend_origin="http://localhost:5173/",
        frontend_origins="https://one.example, https://two.example,https://one.example",
    )

    assert app_settings.allowed_frontend_origins == [
        "https://one.example",
        "https://two.example",
        "http://localhost:5173",
    ]


def test_complete_production_configuration_is_valid() -> None:
    app_settings = _production_settings()

    assert app_settings.allowed_frontend_origins == ["https://askhype.example"]


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"ai_provider": "mock"}, "AI_PROVIDER must be 'gemini'"),
        ({"quota_enforcement_enabled": False}, "QUOTA_ENFORCEMENT_ENABLED must be true"),
        ({"supabase_url": None}, "SUPABASE_URL is required"),
        ({"supabase_secret_key": None}, "SUPABASE_SECRET_KEY is required"),
        ({"anonymous_id_pepper": None}, "ANONYMOUS_ID_PEPPER is required"),
        ({"gemini_api_key": None}, "GEMINI_API_KEY is required"),
        ({"frontend_origin": None}, "FRONTEND_ORIGIN or FRONTEND_ORIGINS is required"),
        ({"mock_subscriptions_enabled": True}, "MOCK_SUBSCRIPTIONS_ENABLED must be false"),
        ({"anonymous_prompt_limit": 4}, "ANONYMOUS_PROMPT_LIMIT must be 5"),
    ],
)
def test_unsafe_production_configuration_fails_clearly(override, expected: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _production_settings(**override)

    assert expected in str(exc_info.value)


def test_production_rejects_wildcard_origin() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _production_settings(frontend_origin="*")

    assert "wildcard frontend origins are not allowed" in str(exc_info.value)
