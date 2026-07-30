import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def default_to_mock_provider() -> None:
    settings.ai_provider = "mock"
    settings.gemini_api_key = None
