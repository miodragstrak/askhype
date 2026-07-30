# AskHype Backend

FastAPI backend foundation for AskHype, a mobile-first AI PWA focused on entertainment, tourism, events, travel, and lifestyle across the Balkans.

## Current Scope

This backend currently provides the application shell, environment-based configuration, CORS for the local frontend, a health endpoint, and a structured mock chat endpoint.

The chat endpoint runs in mock provider mode by default. It returns deterministic Serbian demo recommendations and does not call external AI APIs. Gemini integration will be added in a later step.

## Folder Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── api/routes/chat.py
│   ├── api/routes/health.py
│   ├── core/config.py
│   ├── providers/base.py
│   ├── providers/mock.py
│   ├── schemas/chat.py
│   └── services/chat_service.py
├── tests/
│   ├── test_chat.py
│   └── test_health.py
├── .env.example
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.12 or newer

## Setup

Run these commands from the `backend` directory.

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -e ".[dev]"
```

Optionally create a local environment file:

```bash
cp .env.example .env
```

Do not commit real `.env` files or secrets.

## Development

Start the development server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

For local frontend integration, run the React/Vite app from the repository root with `VITE_API_BASE_URL=http://localhost:8000`.

Run tests:

```bash
pytest
```

## Endpoints

`GET /`

```json
{
  "name": "AskHype API",
  "status": "running"
}
```

`GET /api/health`

```json
{
  "status": "ok",
  "environment": "development",
  "ai_provider": "mock"
}
```

`POST /api/chat`

Request:

```json
{
  "message": "Gde mogu da izađem ovog vikenda u Beogradu?",
  "conversation_id": null,
  "location": "Beograd",
  "language": "sr",
  "interests": ["muzika", "noćni život"]
}
```

Response:

```json
{
  "conversation_id": "conv_example",
  "provider": "mock",
  "answer_type": "recommendations",
  "summary": "Za Beograd bih krenuo sa tri opcije koje pokrivaju muziku, dobru atmosferu i malo kulture.",
  "recommendations": [
    {
      "id": "nightlife-koncert-01",
      "title": "Koncert u centru grada",
      "category": "koncert",
      "short_description": "Veče sa živom muzikom i publikom koja dolazi zbog atmosfere, ne samo zbog pića.",
      "location": "Beograd",
      "estimated_price": "1.200-2.500 RSD",
      "date_or_duration": "ovog vikenda",
      "reason": "Dobar izbor ako želiš energičan izlazak bez previše planiranja.",
      "image_url": "https://example.com/images/askhype-koncert.jpg",
      "source_url": "https://example.com/events/concert"
    }
  ],
  "follow_up_actions": [
    "Filtriraj samo događaje za večeras",
    "Dodaj opcije za mirniji izlazak",
    "Predloži plan po satima"
  ],
  "sources": [
    {
      "title": "AskHype mock katalog događaja",
      "url": "https://example.com/askhype/mock-events",
      "last_verified": "2026-01-01T09:00:00Z"
    }
  ],
  "generated_at": "2026-01-01T12:00:00Z"
}
```

Curl example:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Gde mogu da izađem ovog vikenda u Beogradu?",
    "location": "Beograd",
    "language": "sr",
    "interests": ["muzika", "noćni život"]
  }'
```

## Configuration

Configuration is loaded with `pydantic-settings`.

Supported environment variables:

- `APP_NAME`
- `APP_ENV`
- `API_PREFIX`
- `FRONTEND_ORIGIN`
- `AI_PROVIDER`

Safe default values are listed in `.env.example`.

## Mock Provider Mode

`AI_PROVIDER=mock` is the default. The mock provider is deterministic, uses no network, and supports demo scenarios for nightlife, events, travel planning, food, restaurants, and a generic AskHype fallback.

## Limitations

- No authentication
- No database
- No external AI provider integration
- No Supabase integration
- No RAG pipeline
- No external API calls
