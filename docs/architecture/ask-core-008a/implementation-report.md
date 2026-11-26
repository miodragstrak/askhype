# ASK-CORE-008A · Conversation history and cache containment

Baseline `7f5edc6`. The original production incident still has no confirmed reproduction or root cause. This change addresses independently reproduced failure classes and narrows the client isolation boundary.

## Demonstrated failures and fixes

| Reproduction | Mechanism | Fix |
|---|---|---|
| Inject a failed user or assistant insert after receiving a successful generation | User and assistant rows are separate requests. In-memory generation success does not establish durable persistence. A user-insert failure leaves neither message; an assistant-insert failure can leave only the user row. | The conversation is labeled **Nesačuvano** and the active thread offers **Ponovi čuvanje**. The retry uses the existing conversation and message UUIDs, with duplicate-ignoring inserts. It does not generate another reply or consume another prompt. A successful save of another turn does not clear an earlier failure notice. |
| Delay an account-A history request or reply, sign out and switch to account B | Browser callbacks and state formerly outlived the account that launched them. | The conversation shell is keyed by account or guest, with lifetime abort and result guards. PostgREST queries carry the initiating account’s bearer and lifetime signal. The verified browser flow keeps B’s fixture independent even after A’s deferred response is released. |
| Delete a conversation while generation is pending | The previous response handler could recreate it in UI state from its optimistic snapshot. | Mark deletion immediately and ignore the late generation. The delete waits for any tracked persistence operation for that conversation before issuing the database delete. |
| Seed an old runtime cache with synthetic private content and update the service worker | The prior Workbox matcher broadly allowed HTTPS GET responses outside the research exclusion. | Keep static precache and navigation shell support, remove the broad runtime rule, and delete the named legacy `offlineCache` during activation. The upgrade test keeps an unrelated cache and verifies the app reloads and static assets remain cached. |

## Preventive hardening

- Account transitions discard previous transcript, error, pending attachment and quota state. A delayed ordinary response updates only its originating conversation, and background errors do not replace the currently selected thread’s error state. Opening a thread reads hydrated data synchronously, so there are no per-thread requests to resolve in reverse order. Tests cover switching to an existing thread while a submission is pending.
- Add stable tie-breakers to history and message queries. Treat an update that returns no row as missing. The client scopes private Supabase and selected API GETs with `cache: no-store` as an extra browser HTTP-cache control.
- History diagnostics report an operation, temporary correlation ID, account/guest/loading category, duration, outcome, safe error category, and a conversation UUID when available. Authentication, permission, network, persistence, local storage, stale response and missing row are distinct. Raw errors, content, user IDs, bearer credentials and email are excluded. Diagnostics are client-console events with no new telemetry service.

## Implementation map

- `AskHypeShell.tsx` owns the account lifetime, hydrate guards, submission and persistence lifecycle, navigation, deletion, and save retry. `ConversationSidebar.tsx` and `ConversationHistoryItem.tsx` display the unsaved state. [Shell](../../../src/components/askhype/AskHypeShell.tsx) · [Sidebar](../../../src/components/askhype/ConversationSidebar.tsx)
- `SupabaseConversationRepository` pins request ownership, classifies errors and orders reads. `initializeAuthenticatedHistory` can keep remote history available when the local import marker cannot be stored. `historyDiagnostic` emits allowlisted fields. [Repository](../../../src/services/conversation-repository.ts) · [Diagnostics](../../../src/services/history-diagnostics.ts)
- `UsageProvider` binds usage state to its owning account lifetime. The Supabase client and API GET helpers opt out of browser HTTP caching. [Usage](../../../src/usage/UsageProvider.tsx) · [Client](../../../src/utils/supabase.ts) · [API helpers](../../../src/services/chat-api.ts)
- `vite.config.ts` preserves Workbox precache, and `history-cache-upgrade.js` retires the obsolete runtime cache. [Vite config](../../../vite.config.ts) · [Upgrade handler](../../../public/history-cache-upgrade.js)

## Verification

- Browser suite uses real Chromium, a production frontend build with synthetic configuration, two mock accounts and a loopback-only HTTP fixture. Run `node tests/browser/history.mjs` from the repository root with Node 22 and Chromium installed. Set `CHROME_BIN` if needed. The runner uses port 4178 and an isolated temporary browser profile. [Browser harness](../../../tests/browser/history.mjs)
- Vitest uses repository and state simulations. It does not execute browser caching, Supabase RLS or real authentication. Backend regression tests preserve quota, Presentation V3 and Deep Research coverage. The browser reopens a completed research conversation from a persisted fixture.
- Passed on Chromium with synthetic auth and HTTP services: create, reply and reload; user/assistant save failures and save-only retry; delayed reads and replies across account transitions; navigation and deletion during a pending reply; two tabs with refresh and ordering; completed research reopening; legacy cache cleanup, private GET exclusion, and offline app-shell reload.
- Backend pytest reported 631 passed and one opt-in video integration skip. Frontend Vitest reported 36 passed. Lint, TypeScript, production build and Git whitespace checks passed. Vite reports its existing large-bundle warning. The pre-existing grounding diagnostic edits and ASK-CORE-001 audit were preserved.

## Rollout and remaining limits

Use an isolated staging frontend and synthetic users first. Verify upgrade from an installed worker, cache inspection, switching accounts, and offline shell reload. The cleanup runs when the new worker activates. An old installed worker can retain its behavior until it receives the update. Avoid rolling back to the old broad cache matcher. If the history UI needs rollback, retain the cache containment changes in the rollback build and verify old clients can read the unchanged schema.

Separate writes remain vulnerable to abrupt tab close or reload. Unsaved text and save retries are retained in the active account session only. Tabs converge on refresh and do not provide realtime synchronization. Stable IDs avoid duplicate writes during save-only retry, while a generation retry after an ambiguous HTTP outcome can still rerun provider work. Query pagination and true Supabase authorization are outside the browser fixture. Historical guest import remains device-local according to the existing policy.

**Next task:** ASK-CORE-008B should introduce server-owned, idempotent turn settlement and paginated history with deterministic ordering. Review transactional boundaries, loss of HTTP response, retry recovery, and authorization using an isolated Supabase environment before any migration.
