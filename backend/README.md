# AskHype Backend

FastAPI backend foundation for AskHype, a mobile-first AI PWA focused on entertainment, tourism, events, travel, and lifestyle across the Balkans.

## Current Scope

This backend currently provides the application shell, environment-based configuration, CORS for the local frontend, and a health endpoint. It does not include authentication, database integration, external AI providers, RAG, or third-party APIs.

AI integration will be added in a later step.

## Folder Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── api/routes/health.py
│   ├── core/config.py
│   ├── providers/
│   ├── schemas/
│   └── services/
├── tests/
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

## Configuration

Configuration is loaded with `pydantic-settings`.

Supported environment variables:

- `APP_NAME`
- `APP_ENV`
- `API_PREFIX`
- `FRONTEND_ORIGIN`
- `AI_PROVIDER`

Safe default values are listed in `.env.example`.

## Limitations

- No authentication
- No database
- No external AI provider integration
- No Supabase integration
- No RAG pipeline
- No external API calls
