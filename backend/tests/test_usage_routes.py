import asyncio

import httpx

from app.main import app

GUEST_ID = "77777777-7777-4777-8777-777777777777"


def test_missing_guest_header_returns_400() -> None:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/chat", json={"message": "Plan"})

    response = asyncio.run(request())

    assert response.status_code == 400


def test_malformed_guest_header_returns_400() -> None:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/usage", headers={"X-Anonymous-ID": "bad"})

    response = asyncio.run(request())

    assert response.status_code == 400


def test_usage_endpoint_and_chat_headers_for_guest() -> None:
    async def request() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            headers = {"X-Anonymous-ID": GUEST_ID}
            before = await client.get("/api/usage", headers=headers)
            chat = await client.post("/api/chat", headers=headers, json={"message": "Plan za Bor"})
            return before, chat

    before, chat = asyncio.run(request())

    assert before.status_code == 200
    assert before.json()["used"] == 0
    assert chat.status_code == 200
    assert chat.headers["X-AskHype-Plan"] == "guest"
    assert chat.headers["X-AskHype-Usage-Limit"] == "3"


def test_quota_exhausted_returns_structured_429(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "anonymous_prompt_limit", 1)

    async def request() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            headers = {"X-Anonymous-ID": GUEST_ID}
            first = await client.post("/api/chat", headers=headers, json={"message": "Prvo"})
            second = await client.post("/api/chat", headers=headers, json={"message": "Drugo"})
            return first, second

    first, second = asyncio.run(request())

    assert first.status_code == 200
    assert second.status_code == 429
    detail = second.json()["detail"]
    assert detail["code"] == "prompt_limit_reached"
    assert detail["identity"] == "guest"
    assert detail["plan"] == "guest"
    assert detail["remaining"] == 0
