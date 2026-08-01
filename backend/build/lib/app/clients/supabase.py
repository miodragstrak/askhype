from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.core.config import Settings, settings
from app.providers.exceptions import AIProviderConfigurationError


def _secret_value(value: object) -> str:
    if hasattr(value, "get_secret_value"):
        return str(value.get_secret_value())
    return str(value)


def validate_supabase_server_config(app_settings: Settings = settings) -> None:
    if not app_settings.quota_enforcement_enabled:
        return
    if not app_settings.supabase_url:
        raise AIProviderConfigurationError("Supabase server URL is not configured.")
    if app_settings.supabase_secret_key is None:
        raise AIProviderConfigurationError("Supabase server secret is not configured.")
    if app_settings.anonymous_id_pepper is None:
        raise AIProviderConfigurationError("Anonymous identity pepper is not configured.")


@lru_cache
def get_supabase_admin_client() -> Client:
    validate_supabase_server_config(settings)
    if not settings.supabase_url or settings.supabase_secret_key is None:
        raise AIProviderConfigurationError("Supabase server client is not configured.")
    return create_client(
        settings.supabase_url,
        _secret_value(settings.supabase_secret_key),
    )


class SupabaseAuthVerifier:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or get_supabase_admin_client()

    async def verify_claims(self, token: str) -> dict[str, object]:
        result = self.client.auth.get_claims(jwt=token)
        claims = getattr(result, "claims", None) or result
        if hasattr(claims, "model_dump"):
            claims = claims.model_dump()
        if not isinstance(claims, dict):
            raise ValueError("Invalid Supabase claims response.")
        return claims
