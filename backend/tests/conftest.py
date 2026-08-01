import pytest

from app.api import dependencies
from app.core.config import settings


@pytest.fixture(autouse=True)
def default_to_mock_provider() -> None:
    settings.ai_provider = "mock"
    settings.gemini_api_key = None
    settings.quota_enforcement_enabled = False
    settings.anonymous_id_pepper = "test-pepper"
    dependencies._memory_usage_repository.events.clear()
    dependencies._memory_usage_repository.plans.clear()
