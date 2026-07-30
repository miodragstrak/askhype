from fastapi.testclient import TestClient

from app.main import app


def test_chat_nightlife_request_returns_mock_recommendations() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "Gde mogu da izađem ovog vikenda u Beogradu?",
                "location": "Beograd",
                "language": "sr",
                "interests": ["muzika", "noćni život"],
            },
        )

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
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "Predloži vikend putovanje po Crna Gora ili Balkan",
                "location": "Beograd",
                "interests": ["more", "planina"],
            },
        )

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
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422
