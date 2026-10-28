from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AskHype API"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    api_prefix: str = "/api"
    frontend_origin: str | None = None
    frontend_origins: str | None = None
    ai_provider: Literal["mock", "gemini"] = "mock"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: int = Field(default=45, gt=0)
    gemini_temperature: float = 0.4
    gemini_max_output_tokens: int = Field(default=4096, gt=0)
    quota_enforcement_enabled: bool = False
    supabase_url: str | None = None
    supabase_secret_key: SecretStr | None = None
    anonymous_id_pepper: SecretStr | None = None
    anonymous_prompt_limit: int = Field(default=5, gt=0)
    free_rolling_24h_prompt_limit: int = Field(
        default=10,
        gt=0,
        validation_alias=AliasChoices("FREE_ROLLING_24H_PROMPT_LIMIT", "FREE_MONTHLY_PROMPT_LIMIT"),
    )
    premium_rolling_24h_prompt_limit: int = Field(
        default=200,
        gt=0,
        validation_alias=AliasChoices("PREMIUM_ROLLING_24H_PROMPT_LIMIT", "PREMIUM_MONTHLY_PROMPT_LIMIT"),
    )
    mock_subscriptions_enabled: bool = True

    @property
    def allowed_frontend_origins(self) -> list[str]:
        configured = [
            *(self.frontend_origins or "").split(","),
            self.frontend_origin or "",
        ]
        origins = [_normalize_origin(value) for value in configured if value.strip()]
        if not origins and self.app_env != "production":
            return ["http://localhost:5173"]
        return list(dict.fromkeys(origins))

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        origins = self.allowed_frontend_origins
        if self.app_env != "production":
            return self

        errors: list[str] = []
        if self.ai_provider != "gemini":
            errors.append("AI_PROVIDER must be 'gemini'")
        if not self.quota_enforcement_enabled:
            errors.append("QUOTA_ENFORCEMENT_ENABLED must be true")
        if not _has_text(self.supabase_url):
            errors.append("SUPABASE_URL is required")
        if not _has_secret(self.supabase_secret_key):
            errors.append("SUPABASE_SECRET_KEY is required")
        if not _has_secret(self.anonymous_id_pepper):
            errors.append("ANONYMOUS_ID_PEPPER is required")
        if not _has_secret(self.gemini_api_key):
            errors.append("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        if not origins:
            errors.append("FRONTEND_ORIGIN or FRONTEND_ORIGINS is required")
        if "*" in origins:
            errors.append("wildcard frontend origins are not allowed")
        if self.mock_subscriptions_enabled:
            errors.append("MOCK_SUBSCRIPTIONS_ENABLED must be false")
        if self.anonymous_prompt_limit != 5:
            errors.append("ANONYMOUS_PROMPT_LIMIT must be 5")
        if self.free_rolling_24h_prompt_limit != 10:
            errors.append("FREE_ROLLING_24H_PROMPT_LIMIT must be 10")
        if self.premium_rolling_24h_prompt_limit != 200:
            errors.append("PREMIUM_ROLLING_24H_PROMPT_LIMIT must be 200")

        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


def _has_secret(value: SecretStr | None) -> bool:
    return bool(value and value.get_secret_value().strip())


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _normalize_origin(value: str) -> str:
    origin = value.strip().rstrip("/")
    if origin == "*":
        return origin
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Invalid frontend origin: {value!r}. Use scheme and host only.")
    return origin


settings = Settings()
