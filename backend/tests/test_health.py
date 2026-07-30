import asyncio

import httpx

from app.main import app


def test_health_check_returns_default_status() -> None:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/health")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "development",
        "ai_provider": "mock",
    }
