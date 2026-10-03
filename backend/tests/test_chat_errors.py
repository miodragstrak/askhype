import asyncio

import httpx

from app.main import app
from app.providers.exceptions import AIProviderUnavailableError
from app.services.chat_service import ChatService

ANONYMOUS_HEADERS = {"X-Anonymous-ID": "22222222-2222-4222-8222-222222222222"}


def test_provider_error_http_response_does_not_expose_secret(monkeypatch) -> None:
    secret = "super-secret-gemini-key"

    async def raise_unavailable(self, request):
        raise AIProviderUnavailableError(f"rate limited: {secret}")

    monkeypatch.setattr(ChatService, "generate_response", raise_unavailable)

    async def request() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            failed = await client.post(
                "/api/chat",
                headers=ANONYMOUS_HEADERS,
                json={"message": "Plan za večeras"},
            )
            usage = await client.get("/api/usage", headers=ANONYMOUS_HEADERS)
            return failed, usage

    response, usage = asyncio.run(request())

    assert response.status_code == 503
    assert secret not in response.text
    assert "AI provider trenutno nije dostupan" in response.text
    assert usage.status_code == 200
    assert usage.json()["used"] == 0
