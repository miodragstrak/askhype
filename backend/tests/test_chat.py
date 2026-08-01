import asyncio

import httpx

from app.main import app

ANONYMOUS_HEADERS = {"X-Anonymous-ID": "11111111-1111-4111-8111-111111111111"}


def test_chat_nightlife_request_returns_mock_recommendations() -> None:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/chat",
                headers=ANONYMOUS_HEADERS,
                json={
                    "message": "Gde mogu da izađem ovog vikenda u Beogradu?",
                    "location": "Beograd",
                    "language": "sr",
                    "interests": ["muzika", "noćni život"],
                },
            )

    response = asyncio.run(request())

    data = response.json()

    assert response.status_code == 200
    assert data["provider"] == "mock"
    assert data["conversation_id"]
    assert len(data["recommendations"]) == 3
    assert "Beograd" in data["summary"]
    assert "izlazak" in " ".join(data["follow_up_actions"]).casefold()
    assert data["follow_up_actions"]
    assert data["sources"]
    assert data["generated_at"]


def test_chat_travel_request_returns_travel_recommendations() -> None:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/chat",
                headers=ANONYMOUS_HEADERS,
                json={
                    "message": "Predloži vikend putovanje po Crna Gora ili Balkan",
                    "location": "Beograd",
                    "interests": ["more", "planina"],
                },
            )

    response = asyncio.run(request())

    data = response.json()
    recommendation_text = " ".join(
        [item["title"] + " " + item["category"] + " " + item["location"] for item in data["recommendations"]]
    )

    assert response.status_code == 200
    assert len(data["recommendations"]) == 3
    assert "Kotor" in recommendation_text
    assert "Žabljak" in recommendation_text
    assert "Budva" in recommendation_text
    assert "putovanje" in recommendation_text.casefold()


def test_chat_empty_message_returns_validation_error() -> None:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/chat", headers=ANONYMOUS_HEADERS, json={"message": ""})

    response = asyncio.run(request())

    assert response.status_code == 422
