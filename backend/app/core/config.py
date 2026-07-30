from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AskHype API"
    app_env: str = "development"
    api_prefix: str = "/api"
    frontend_origin: str = "http://localhost:5173"
    ai_provider: str = "mock"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: int = Field(default=45, gt=0)
    gemini_temperature: float = 0.4
    gemini_max_output_tokens: int = Field(default=4096, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
