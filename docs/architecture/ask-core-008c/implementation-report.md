# ASK-CORE-008C · Client disconnect resilience

The FastAPI lifespan owns a per-worker supervisor. An authenticated turn POST validates and materializes the request before handing its typed input and repository to a tracked task. The task owns database admission, generation and settlement. The HTTP handler awaits it through a shield. Cancelling the waiter leaves the task running. There is no request stream, response writer, or yield-scoped resource in the supervised operation. PostgreSQL remains the authority for claims, fingerprints, ownership, quota and terminal transitions.

## Settings and boundaries

- `SERVER_CHAT_TURNS_ENABLED` and `VITE_SERVER_CHAT_TURNS_ENABLED` retain their default-off behavior. The existing authenticated turn route and durable quota requirement are preserved.
- `CHAT_TURN_WORKER_CAPACITY` defaults to 16 per worker (range 1–128). Saturated or draining workers respond HTTP 503 before claiming a new turn. A duplicate POST can also receive 503 under saturation; the status GET stays available without a supervisor slot.
- `CHAT_TURN_SHUTDOWN_DRAIN_SECONDS` defaults to 15 seconds (range 0–120). On lifespan shutdown the supervisor stops admission, waits for tasks, cancels remaining work, and waits at most one additional second for cancellation to be observed. Uvicorn and the host may have their own earlier ingress and termination deadlines.
- Admission and each of the two settlement attempts have a 10-second application deadline. The turn-specific Supabase client has an 8-second PostgREST transport timeout. Generation retains its 120-second application ceiling and the provider's existing timeout. Under cooperative cancellation the full budget is 150 seconds including admission. This leaves approximately 30 seconds before the existing three-minute reconciliation threshold. A blocking call or process scheduling delay can exceed an application deadline. In-flight database work can still commit after the caller loses its acknowledgment. Existing row locks and terminal settlement rules decide late races.
- Lifecycle logs carry an event, generated turn UUID, process instance, elapsed milliseconds and safe outcome/category fields. No prompt, answer, token, header or user identity is logged. A transport disconnect alone may leave the waiter running until response delivery. It is distinct from observed waiter cancellation, provider timeout, settlement error, lifespan shutdown or process loss.

## Release and rollback

On isolated staging, deploy the candidate backend with the existing schema and rollout controls. Keep the first smoke test synthetic and use an independently controlled delayed provider fixture so refresh and tab close happen after execution starts. Verify the original turn becomes completed, a new connection can recover it, one assistant message is stored and one usage reservation completes. Check logs for instance and stage, and separately test a hard stop that leaves the existing reconciliation to mark the claim unknown. Use actual Gemini only with separate authorization. Verify legacy guest, presentation and Deep Research endpoints through their existing checks.

No migration or frontend build is required by this change. If rollback is necessary, keep the database state and follow the existing flag sequencing from 008B. A hard process kill, host restart, or a lost admission acknowledgment at the database deadline can leave an unresolved claim. The current PostgreSQL recovery deliberately does not redispatch uncertain work. This change provides client-disconnect resilience while the accepting process survives. It does not make provider execution durable across restarts.

## Local validation commands

```bash
cd backend && .venv/bin/pytest -q
# From the repository root
PG_BIN=/usr/lib/postgresql/17/bin RUN_CHAT_TURN_PROCESS_TESTS=1 \
  CHAT_TURN_TEST_PYTHON=.venv/bin/python bash backend/scripts/validate_chat_turns_postgres.sh
npm run test:frontend
npm run lint
npx tsc --noEmit
npm run build
node tests/browser/history.mjs --durable
node tests/browser/history.mjs
git diff --check
```

The TCP tests close a real socket and inject waiter cancellation after observing ASGI disconnect. The two-process test uses local Uvicorn processes, a gated mock provider, and the real SQL RPCs through a disposable PostgreSQL Unix socket. It tests concurrent duplicate claims, child-process termination, and recovery from the surviving backend. These tests do not exercise hosted PostgREST, Render proxy behavior, or an external provider.

## Results

- Backend regression suite: 645 passed, 2 skipped. The two-process test is opt-in and passed separately. The remaining skip is the opt-in video integration.
- Disposable PostgreSQL 17: fresh and upgrade checks passed. Two independent backend processes shared the test database. A real TCP close with waiter cancellation recovered the reply through the other process, with one provider invocation, one assistant row and one completed reservation. The hard-kill control reached unknown without redispatch.
- Frontend Vitest: 37 passed. Lint, TypeScript, production build, Git whitespace checks, and both legacy and durable Chromium suites passed. Vite emitted its bundle-size warning.
