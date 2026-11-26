# ASK-CORE-008B · Server-owned ordinary chat turns

## Execution and ownership

Previously the browser inserted the user message and assistant reply separately around the ordinary chat request. A tab close or failed write could leave the account transcript incomplete. With both flags enabled, authenticated ordinary chat (including image attachments) posts a stable UUID to `POST /api/chat/turns/{turn_id}`. The route uses the existing authenticated identity dependency and existing chat parser. Guests, flag-off clients, explicit document actions, presentations, animation and Deep Research retain their existing endpoints and persistence behavior.

1. **Admission transaction.** `accept_chat_turn` serializes claims for the request UUID, checks the existing owner and request fingerprint, verifies or creates the owned conversation, calls the existing quota reservation RPC and inserts the user row and processing state. Quota denial admits neither a turn nor a new thread. The request ID is also the user message ID. The usage event and assistant message use independent server-allocated UUIDs.
2. **Execution.** Only the transaction winner invokes `ChatService.generate_response`. The existing routing, provider, model, grounding and citations are preserved. The request handler has a 120-second application execution ceiling. No database transaction spans the provider call. The fingerprint includes ordered validated image content hashes, MIME types and the normalized chat request. Chat history continues to come from the existing frontend context window. File bytes and raw provider output are not stored by this feature.
3. **Settlement transaction.** `settle_chat_turn` locks the owned conversation and turn, inserts the assistant into the existing message table, finalizes the original reservation and marks the turn complete. The assistant row contains the typed response and citations. The turn row links to it without a second response copy. Provider name is available in the response and quota row. Exact model attribution is unavailable on the current ChatService response contract. One bounded settlement retry reuses the in-memory response and never dispatches generation.
4. **Recovery.** `GET /api/chat/turns/{turn_id}` is owner-scoped and private no-store. A replay of an identical accepted POST returns the existing result, or HTTP 202 when processing. A different fingerprint or thread under the same owner returns HTTP 409. Another account receives HTTP 404. A terminal response is read from the assistant row. The browser can recover by ID after a lost response or page reload.

## States and accounting

| State | Trigger | Quota and recovery |
|---|---|---|
| Rejected before acceptance | Invalid input, absent owned thread, conflicting ID, authorization, or quota denial | No new reservation. |
| Processing | Accepted user row and reservation commit together | Reservation counts under the existing 10-minute policy. Duplicate execution is suppressed. Acceptance and the initial processing claim happen in one transaction. |
| Completed | Assistant and quota finalize in the same transaction | One completed reservation. Replay and history reads are free. A lost HTTP or DB acknowledgment after commit recovers the same reply. |
| Failed | Known provider/configuration error | Reservation is finalized as failed using existing counting rules. A new prompt requires user action and a new turn ID. |
| Unknown | Timeout, ambiguous provider unavailability, unexpected error, or an abandoned processing claim on a status read after three minutes | No replay of potentially executed work. Status becomes terminal and the reservation is finalized as failed when possible. If no one reads it, the existing quota expiry policy still applies. |
| Deleted | Conversation deletion cascades accepted turns and messages | A tombstone prevents an accepted UUID from being claimed anew while the account exists. Unsettled quota is released; completed usage is retained. |

Cancellation or process loss can occur after the admission commit and before or after upstream dispatch. Status recovery maps an expired claim to unknown because database state cannot establish whether the provider ran. A response generated upstream but lost before settlement cannot be recovered from this implementation. There is no durable worker or external provider idempotency guarantee. The provider’s existing internal retry policy stays in effect.

## Paginated history and UI

Feature-on history uses the existing authenticated PostgREST/RLS boundary. The repository fetches up to 30 threads per page ordered by `updated_at DESC, id DESC`. It lazily fetches the active thread's messages, using `created_at DESC, id DESC` for the cursor and chronological display. The sidebar and thread load older pages explicitly. The UI merges by ID, preserves earlier pages across navigation in the same account session, and retains the account lifetime and deletion guards from 008A. A normal turn updates only its thread. The browser reads the latest unresolved ordinary turn on opening or refresh and polls its owned status for a bounded period. It only resends a missing submission by explicit user action and with the original ID and payload held in memory. A request aborted before acceptance can still be lost on refresh. Legacy and research messages remain readable using the same rows and response schema.

The cursor is deterministic for a stable dataset. A thread updated by another tab can move to an earlier page while scrolling. Refresh reconciles the list; there is no realtime cross-tab feed. There is no upload rehydration or automatic redispatch after a restart.

## Migration and rollback

The new additive migration creates a turn table, a deleted-ID table, indexes, and service-only admission/read/settle RPCs. Restrictive RLS policies protect server-marked ordinary rows from direct authenticated writes while leaving legacy and specialty rows writable under their existing policies. Parent conversation deletion still cascades. The existing quota and research migrations are intact. DDL takes normal schema/index locks; review table size and deployment window on the target database before applying. No live migration was run.

After approval, provision isolated staging Supabase/auth and credentials first. Apply the migration and validate the PostgREST schema cache and service role, deploy the backend with `SERVER_CHAT_TURNS_ENABLED` off, then enable it with durable quota enforcement for staging. Build the staging frontend with `VITE_SERVER_CHAT_TURNS_ENABLED=true`. Both flags default off. Exercise both transport contracts and confirm proxy deadlines and authorization, then approve any broader release separately. Do not apply a staging migration against a shared production project for trial purposes.

For rollback, turn off the frontend flag first. Leave the read path available temporarily for existing clients and pending status recovery, then disable the backend flag or restore the earlier backend artifact. Keep the additive schema and existing private-cache containment. An earlier client can read completed turns as ordinary conversation messages. Do not drop the journal, tombstones, or policies as a routine rollback. Investigate processing rows and settle as unknown where appropriate, without dispatching provider work again.

## Changed files and verification

- Backend flags and routes in [config.py](../../../backend/app/core/config.py) and [chat.py](../../../backend/app/api/routes/chat.py) expose the new submit/status contract. [chat_turns.py](../../../backend/app/services/chat_turns.py) implements fingerprinting, RPC access and claimed execution.
- [SQL migration](../../../supabase/migrations/202611260001_ask_core_008b_chat_turns.sql) implements ownership, claim, transaction settlement, terminal recovery and indexes.
- [AskHypeShell](../../../src/components/askhype/AskHypeShell.tsx) owns browser admission/recovery and history paging state. [ConversationSidebar](../../../src/components/askhype/ConversationSidebar.tsx) exposes older threads. [Chat client](../../../src/services/chat-api.ts), [conversation repository](../../../src/services/conversation-repository.ts) and [message types](../../../src/types/conversation.ts) support the new contracts.
- [ASGI tests](../../../backend/tests/test_chat_turns.py) use a synthetic provider and repository. [PostgreSQL validation runner](../../../backend/scripts/validate_chat_turns_postgres.sh) and its [assertions](../../../backend/scripts/chat_turn_postgres_assertions.sql) use a disposable local Unix socket and verify fresh install and upgrade, competing database claims, lookup/ownership, atomic rollback on failed assistant insert and failed quota update, expiry, deletion and cursor ties.
- [Chromium harness](../../../tests/browser/history.mjs) tests the existing path by default and the new path with `--durable`. It uses a real browser with synthetic auth, HTTP and database fixtures, including cache upgrade, offline shell reload, account switching, reloading during processing, lost HTTP acknowledgment, duplicate submit across tabs, pagination and completed research history. [Vitest cursor coverage](../../../src/services/conversation-repository.test.ts) asserts the compound cursor and input shape.

## Results

- Backend pytest: 638 passed, one opt-in video integration skip.
- Frontend Vitest: 37 passed. Lint, TypeScript, production build and Git whitespace checks passed. Vite emitted its existing bundle-size warning.
- Disposable PostgreSQL 17: fresh and representative pre-migration history upgrade passed. Both exercised a real concurrent claim, quota denial, atomic rollback, cross-user protection, linked Deep Research completion and deleted-turn replay protection.
- Real Chromium, synthetic HTTP/services: legacy and feature-on suites passed. Run the browser commands independently with Node 22 and local Chromium. The PostgreSQL runner uses a fresh cluster as a non-root user and only its private Unix socket.

```bash
PG_BIN=/usr/lib/postgresql/17/bin bash backend/scripts/validate_chat_turns_postgres.sh
node tests/browser/history.mjs
node tests/browser/history.mjs --durable
```

## Release evidence and outstanding risks

Demonstrated guarantees are scoped to the local test layers above. PostgreSQL validates the actual transactions and policies. The ASGI and Chromium runs simulate provider replies and transport faults. They do not validate live Supabase REST deployment behavior, provider billing or request execution after a real backend stop. Production credential mapping, staging isolation, proxy behavior and shared-worker conditions remain untested. ASK-CORE-008A protections and the existing grounding diagnostic patch were preserved.

**Recommended next task:** rehearse the additive migration and a flag-on UAT on isolated staging using synthetic accounts. If the product requires execution to continue across backend restarts, design a leased worker/outbox and provider-idempotency policy as separate work.
