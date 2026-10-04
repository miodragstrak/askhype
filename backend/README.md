# AskHype Backend

FastAPI backend foundation for AskHype, a mobile-first AI PWA focused on entertainment, tourism, events, travel, and lifestyle across the Balkans.

## Current Scope

This backend currently provides the application shell, environment-based configuration, CORS for the local frontend, a health endpoint, structured chat, Supabase identity verification, server-side prompt usage quotas, and controlled mock Premium activation for allowlisted demo users.

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

Registered free users may reserve 10 prompts and Premium users 200 prompts in the immediately preceding 24 hours. The guest limit remains server-configurable. `completed` events count for 24 hours; `reserved` events count for up to 10 minutes while generation is in progress. `failed` events and reservations automatically marked stale do not count.

When a prompt quota is exhausted, `POST /api/chat` returns HTTP 429 with a structured `detail.code` of `prompt_limit_reached`. Successful `ChatResponse` bodies remain unchanged; usage counts are exposed through `X-AskHype-*` response headers. `reset_at` is the time when the oldest currently counted event leaves the rolling window, or `null` when no events count.

`GET /api/mock-subscription`

Requires `Authorization: Bearer <supabase-access-token>`. Guests receive 401.

```json
{
  "enabled": true,
  "eligible": true,
  "plan": "free",
  "is_mock": true
}
```

`POST /api/mock-subscription/activate`

Activates demo Premium only for the current authenticated user when `can_activate_mock_premium=true` in `public.profiles`.

```json
{
  "status": "active",
  "plan": "premium",
  "is_mock": true,
  "message": "Demo Premium paket je aktiviran."
}
```

`POST /api/mock-subscription/deactivate`

Returns an eligible demo user to the free plan for repeat testing.

```json
{
  "status": "inactive",
  "plan": "free",
  "is_mock": true,
  "message": "Nalog je vraćen na besplatan paket."
}
```

These endpoints never accept `user_id`, email, plan, or eligibility from the request body. Eligibility is trusted only from the server-side Supabase profile row. Ordinary users receive 403 with `detail.code=mock_premium_not_allowed`. Missing profiles return a safe 404.

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
- `FREE_ROLLING_24H_PROMPT_LIMIT`
- `PREMIUM_ROLLING_24H_PROMPT_LIMIT`
- `MOCK_SUBSCRIPTIONS_ENABLED`

Safe default values are listed in `.env.example`.

Set `QUOTA_ENFORCEMENT_ENABLED=true` only when Supabase server configuration is present. `SUPABASE_SECRET_KEY` and `ANONYMOUS_ID_PEPPER` are server-only secrets and must not be exposed to the frontend.

Set `MOCK_SUBSCRIPTIONS_ENABLED=false` to disable the mock Premium activation endpoints safely.

The legacy `FREE_MONTHLY_PROMPT_LIMIT` and `PREMIUM_MONTHLY_PROMPT_LIMIT` names remain accepted for one transition period when their new rolling-window equivalents are not set. The authenticated limits are product contract values and must remain 10 and 200 in production. Reservations have a fixed 10-minute stale timeout in both the application and migration.

## Supabase Quota Migration

The repository owns the minimum quota schema in `supabase/migrations/202609190001_hype_ask_002_rolling_quotas.sql`. It creates or extends `public.profiles` and `public.usage_events`, adds indexes, enables RLS, and installs service-role-only `reserve_prompt_usage` and `finalize_prompt_usage` RPCs.

Apply migrations to a linked staging project from the repository root:

```bash
supabase db push
```

If the Supabase CLI is not part of your deployment workflow, review and run the migration once through the staging SQL editor before production. The migration preserves rows and uses guarded DDL. It intentionally aborts if existing profile plans are not `free`/`premium`, usage statuses are unsupported, or a usage row does not have exactly one of `user_id` and `anonymous_id_hash`. Resolve those incompatibilities with an explicit, reviewed data migration; do not rename or copy a legacy raw anonymous-ID column automatically.

The migration assumes an existing table does not have additional required columns without defaults that would reject the documented inserts, and that `profiles.user_id` remains its conflict key. Inspect those properties in staging before applying it to a project whose schema predates these repository migrations.

The reservation RPC serializes requests per user or anonymous hash with a transaction-scoped advisory lock. It derives authenticated limits from the server-owned profile plan, ignores the caller's anonymous limit for authenticated users, and performs expiration, count, and insert in one transaction. Browser roles cannot execute either quota RPC or write usage events. Authenticated users can read their profile and update only preference columns; grants prevent them from changing `plan` or mock-Premium eligibility.

Staging verification after migration:

1. Confirm browser `anon` and `authenticated` clients cannot insert/update/delete `usage_events` or execute either RPC.
2. Send 11 concurrent free-user reservations and confirm exactly 10 succeed; repeat with 201 Premium reservations and confirm exactly 200 succeed.
3. Finalize one reservation as `failed` and confirm the next reservation succeeds.
4. Insert controlled staging events around the 24-hour boundary and verify `/api/usage` counts only events inside the window.
5. Leave a reservation unfinished for more than 10 minutes and confirm a subsequent reservation marks it failed with `failure_code=stale_reservation`.

Rollback should restore the previous backend before removing database objects. The additive tables and columns can remain safely. If the RPCs must be disabled immediately, revoke their `service_role` execute grants. Dropping tables or columns is deliberately not included because that could destroy production data; destructive rollback requires a separate reviewed migration and backup.

## Demo Premium Administration

Mock Premium is payment-free and controlled by `public.profiles.can_activate_mock_premium`. An admin can mark a selected demo user after registration:

```sql
update public.profiles
set can_activate_mock_premium = true
where user_id = '<registered-user-id>';
```

Activation changes only `public.profiles.plan` for the authenticated user. Deactivation changes that same row back to `free`. The endpoints never modify `can_activate_mock_premium`, never reset usage history, and the next `GET /api/usage` recalculates remaining prompts against the newly active free or premium limit.

## Mock Provider Mode

`AI_PROVIDER=mock` is the default. Generic requests remain deterministic and use no network. Hype-related requests run the bounded Hype retrieval layer first; the mock provider then returns excerpts from actual retrieved content without calling an AI model.

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

For generic requests, Gemini is asked for an internal structured JSON payload containing only model-generated fields: answer type, summary, exactly 3 recommendations, 2 to 4 follow-up actions, and source labels. Hype requests allow 0 to 3 supported recommendations so the model is never required to invent extra items. Both paths use the existing frontend-facing `ChatResponse` schema.

The Gemini request uses a constrained JSON schema derived from the internal Pydantic model. Schema sanitization is context-aware: application field names inside `properties` mappings are never removed, even if a field is named `title`, `default`, or `additionalProperties`. Unsupported schema metadata such as `default` is removed before SDK submission when needed, and `required` entries are checked against sibling `properties` before any request is made. Application-side Pydantic validation remains authoritative after generation.

The backend rejects malformed JSON, empty required content, duplicate or out-of-range follow-up actions, and the wrong recommendation count. Invalid model-provided URLs are returned as `null`; the backend does not invent replacement URLs.

## Location Precedence

AskHype treats a place named in the current user message as more important than the selected application location. For example, if the request context says `Beograd` but the message asks `Šta da posetim u Boru?`, the model is instructed to answer for Bor, not Beograd. When neither the message nor request context gives a clear location, the assistant should ask a short clarification.

The backend passes the selected app location plus an explicit precedence rule to Gemini and relies on the model to interpret natural-language locations. Generic requests have no verified local data or general web search. Hype requests receive only the bounded source excerpts described below; model-written summaries still require factual review.

## Source Verification

Generic requests have no application-side web verification: model-generated source URLs remain `null`, and model memory must not be described as verified. Hype requests retain only citation URLs supplied by retrieval. Their `last_verified` timestamps are application-owned fetch times, including the original fetch time when a cached page is reused; they do not guarantee ticket availability or editorial accuracy.

## Hype-first Retrieval (HYPE-ASK-005)

The empty conversation has four restrained blue Hype suggestions and two neutral generic suggestions. Both use the existing prompt submission flow. Blue source labels identify Hype TV or Hype Production; the composer, primary controls, navigation, and general recommendation cards retain their existing styling.

`ChatService` detects explicit Hype/Hype TV/Hype Production queries and passes a separate `HypeContext` to the configured provider. Generic requests bypass retrieval entirely. No request/response, conversation-storage, auth, quota, or Supabase schema is changed.

The demo retrieval layer uses only HTTPS on `hypetv.rs` and `hypeproduction.rs`, including their `www` aliases. It fetches two category-specific entry points and at most six linked detail pages. TV news and programs use public RSS feeds (or the site's RSS search for more specific queries); Production artists, shows, and concerts use its public catalog pages. TV is prioritized for news/programs, Production for artists/concerts. The layer is not a crawler, persistent index, vector store, or full RAG system.

Bounds: 4-second HTTP timeouts, a 12-second overall retrieval budget, at most two redirects per page, 1 MB decoded content per page, three context documents, and a 16-page in-process cache with a five-minute lifetime. Redirect destinations and extracted links must remain inside the allowlist. Parsing uses XML for RSS and Beautiful Soup for HTML/JSON-LD; website text is passed as untrusted data, never as instructions.

Publication and event dates remain separate. Upcoming events require a fetched detail page with an explicit numeric/Serbian-text date or JSON-LD `startDate`, on or after the current Belgrade date. Past, cancelled, undated, and conflicting-date items are excluded from upcoming results. Historical queries can include past entries. The model may select only retrieved URLs; displayed card titles, excerpts, locations, and dates are copied from those documents, while unverified model prices/images are removed. Gemini writes the summary from the supplied context. Prices, booking availability, model summary accuracy, and site editorial accuracy are not verified.

If evidence is limited or retrieval fails, Hype answers may contain fewer than three cards or no cards. Mock mode reports the missing evidence rather than using its fictional generic event catalog. Gemini may give clearly labelled unverified general background, but no unsupported Hype facts, events, or invented external citation URLs. There is no general external search integration in this milestone. Only currently indexed feed/catalog content and a bounded sample of linked pages are covered; JavaScript-only content and the full archives are not indexed. Follow-up prompts name Hype explicitly because backend multi-turn memory is still unavailable.

Manual smoke tests with the backend running:

1. Click `Šta ima novo na Hype TV?`; confirm source links and `Hype TV` labels.
2. Ask `Koji Hype koncerti uskoro dolaze?`; confirm Production sources and explicit future dates, or an honest insufficient-evidence response.
3. Ask a generic restaurant/travel question; confirm the existing three-card behavior and neutral styling.

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

- Supabase schema and RPC behavior still require staging verification
- No RAG pipeline
- No general web search or external tourism/event API integration; public Hype HTTP retrieval is bounded as described above
- No web search or live source verification
- No stored multi-turn semantic memory
