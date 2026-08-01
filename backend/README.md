# AskHype Backend

FastAPI backend foundation for AskHype, a mobile-first AI PWA focused on entertainment, tourism, events, travel, and lifestyle across the Balkans.

## Current Scope

This backend currently provides the application shell, environment-based configuration, CORS for the local frontend, a health endpoint, structured chat, Supabase identity verification, and server-side prompt usage quotas.

The chat endpoint runs in mock provider mode by default. It can also run against Gemini when configured with `AI_PROVIDER=gemini` and a local `GEMINI_API_KEY`.

## Folder Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── api/routes/chat.py
│   ├── api/routes/health.py
│   ├── core/config.py
│   ├── providers/base.py
│   ├── providers/exceptions.py
│   ├── providers/gemini.py
│   ├── providers/mock.py
│   ├── prompts/askhype.py
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

This installs FastAPI plus the official Google GenAI Python SDK package, `google-genai`.

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

Requires one identity header:

- `Authorization: Bearer <supabase-access-token>` for signed-in users
- `X-Anonymous-ID: <browser-generated-uuid>` for guests

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
  -H "X-Anonymous-ID: 11111111-1111-4111-8111-111111111111" \
  -d '{
    "message": "Gde mogu da izađem ovog vikenda u Beogradu?",
    "location": "Beograd",
    "language": "sr",
    "interests": ["muzika", "noćni život"]
  }'
```

`GET /api/usage`

Returns the current usage snapshot for the same identity headers used by chat:

```json
{
  "identity": "guest",
  "plan": "guest",
  "used": 1,
  "limit": 3,
  "remaining": 2,
  "reset_at": null
}
```

When a prompt quota is exhausted, `POST /api/chat` returns HTTP 429 with a structured `detail.code` of `prompt_limit_reached`. Successful `ChatResponse` bodies remain unchanged; usage counts are exposed through `X-AskHype-*` response headers.

## Configuration

Configuration is loaded with `pydantic-settings`.

Supported environment variables:

- `APP_NAME`
- `APP_ENV`
- `API_PREFIX`
- `FRONTEND_ORIGIN`
- `AI_PROVIDER`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_TIMEOUT_SECONDS`
- `GEMINI_TEMPERATURE`
- `GEMINI_MAX_OUTPUT_TOKENS`
- `QUOTA_ENFORCEMENT_ENABLED`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `ANONYMOUS_ID_PEPPER`
- `ANONYMOUS_PROMPT_LIMIT`
- `FREE_MONTHLY_PROMPT_LIMIT`
- `PREMIUM_MONTHLY_PROMPT_LIMIT`

Safe default values are listed in `.env.example`.

Set `QUOTA_ENFORCEMENT_ENABLED=true` only when Supabase server configuration is present. `SUPABASE_SECRET_KEY` and `ANONYMOUS_ID_PEPPER` are server-only secrets and must not be exposed to the frontend.

## Mock Provider Mode

`AI_PROVIDER=mock` is the default. The mock provider is deterministic, uses no network, and supports demo scenarios for nightlife, events, travel planning, food, restaurants, and a generic AskHype fallback.

Keep mock mode active with:

```bash
AI_PROVIDER=mock
```

Mock mode does not require `GEMINI_API_KEY`.

## Gemini Provider Mode

Gemini mode uses the official Google GenAI SDK and the same frontend-facing `ChatResponse` schema as mock mode.

Local `.env` example:

```bash
AI_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=45
GEMINI_TEMPERATURE=0.4
GEMINI_MAX_OUTPUT_TOKENS=4096
```

Verify your local `backend/.env` value when smoke testing; the provider always uses `GEMINI_MODEL` from settings and does not hardcode the model.

Never commit a real key. Return to mock mode by setting:

```bash
AI_PROVIDER=mock
```

When Gemini mode is enabled without a key, `/api/chat` returns a clear 503 configuration error. Timeouts return 504, invalid structured responses return 502, and provider unavailability or rate limits return 503. Raw SDK errors, stack traces, and secrets are not returned to the frontend.

## Structured Output

Gemini is asked for an internal structured JSON payload containing only model-generated fields: answer type, summary, exactly 3 recommendations, 2 to 4 follow-up actions, and source labels. The backend then validates and normalizes that payload into the existing `ChatResponse`, adding application-owned fields such as `conversation_id`, `provider`, and `generated_at`.

The Gemini request uses a constrained JSON schema derived from the internal Pydantic model. Schema sanitization is context-aware: application field names inside `properties` mappings are never removed, even if a field is named `title`, `default`, or `additionalProperties`. Unsupported schema metadata such as `default` is removed before SDK submission when needed, and `required` entries are checked against sibling `properties` before any request is made. Application-side Pydantic validation remains authoritative after generation.

The backend rejects malformed JSON, empty required content, duplicate or out-of-range follow-up actions, and the wrong recommendation count. Invalid model-provided URLs are returned as `null`; the backend does not invent replacement URLs.

## Location Precedence

AskHype treats a place named in the current user message as more important than the selected application location. For example, if the request context says `Beograd` but the message asks `Šta da posetim u Boru?`, the model is instructed to answer for Bor, not Beograd. When neither the message nor request context gives a clear location, the assistant should ask a short clarification.

The backend does not run a fragile city parser in this step. It passes the selected app location plus an explicit precedence rule to Gemini and relies on the model to interpret natural-language locations. Human review is still required for factual accuracy because there is no live data, maps, web search, database, scraping, or RAG.

## Source Verification

This step does not include web search, grounding, a database, RAG, scraping, or external tourism APIs. Gemini responses must not claim live verification. Source labels may describe unverified AI guidance, and `last_verified` should stay `null` unless a future application-side verification event exists.

## Conversation Context

The chat request passes the current message, selected location, requested language, interests, and any existing `conversation_id` to the provider. The backend preserves `conversation_id` in the response, but true stored multi-turn semantic memory is not implemented yet.

## Manual Gemini Smoke Test

A real Gemini smoke test consumes Gemini API quota. Run it only when you intentionally set a valid local key, start the API, and send one request:

```bash
AI_PROVIDER=gemini GEMINI_API_KEY=... uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Predloži tri ideje za veče u Beogradu","location":"Beograd","language":"sr"}'
```

Do not print or share your key. The automated tests mock the SDK client and never call the real Gemini API.

## Balkan Demo Evaluation

Run the manual demo evaluation from the `backend` directory. Mock mode is safe and does not call external APIs:

```bash
python scripts/evaluate_demo_locations.py --provider mock
python scripts/evaluate_demo_locations.py --provider mock --city Bor
```

Gemini mode sends real requests and consumes Gemini API quota:

```bash
python scripts/evaluate_demo_locations.py --provider gemini --city Bor --delay 2
```

Optional reports:

```bash
python scripts/evaluate_demo_locations.py --provider gemini --delay 2 --output reports/balkan-demo-evaluation.md
python scripts/evaluate_demo_locations.py --provider gemini --output reports/balkan-demo-evaluation.json
```

The report records provider success, summaries, recommendation titles and locations, source URL presence, unverified-data caveats, timing, and pending manual review fields. It does not automatically declare factual correctness.

## Limitations

- No authentication
- No database
- No Supabase integration
- No RAG pipeline
- No external API calls
- No web search or live source verification
- No stored multi-turn semantic memory
