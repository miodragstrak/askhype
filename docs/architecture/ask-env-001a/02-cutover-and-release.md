# Staging cutover, UAT, and production release

**Execution requires separate approval.** This runbook does not authorize creating resources, suspending services, deploying or applying SQL.

## Stop the shared-backend path before repointing staging

The current reconciler is embedded in each FastAPI process. It starts when `QUOTA_ENFORCEMENT_ENABLED=true` and `GEMINI_RESEARCH_MODEL` is non-empty. It selects stale queued/running records without an environment discriminator or lease. Conditional database writes limit settlement races, but they do not prevent multiple provider polls. The individual research status endpoint can reconcile a job independently of the worker. There is no dedicated worker flag or isolation validator. These are configuration and deployment risks. No runtime correction is included. [Worker startup](../../../backend/app/main.py#L22) · [Worker loop](../../../backend/app/services/research_worker.py) · [Active row query](../../../backend/app/repositories/research_repository.py#L69) · [Research routes](../../../backend/app/api/routes/research.py)

1. **Identify the actual services.** Record which Vercel project, deployment alias and build scope serve each hostname, which frontend sends traffic to each backend, and which Supabase and Gemini projects each backend instance uses. Check every Render replica, legacy staging endpoint, scheduled process and environment group for shared bindings. Record only project refs, service IDs and yes/no comparisons, without keys. Stop if a candidate staging component also serves production. Provision a dedicated replacement after approval in that case.
2. **Quiesce old staging.** Freeze staging traffic and auto-deploy. Suspend or fully stop every confirmed staging-only process with the old shared-project binding. Verify in the platform that no old replicas remain during any rolling deployment. Disable access to reachable old staging API revisions and preview URLs where operators control them. A frontend switch alone leaves workers running. Setting the model unset only in the next revision does not stop an existing process. Do not suspend production, revoke shared production credentials, reassign existing jobs, or modify production records.
3. **Establish new staging boundaries.** Create and bootstrap the new Supabase project as described in [configuration and bootstrap](01-configuration-and-bootstrap.md). Configure staging-only Auth and keys. Use distinct billing and Auth settings. Approve access controls on the staging frontend and use an isolated browser profile with no real accounts.
4. **Start staging with research disabled.** Assign the staging Render service its new Supabase URL/key and pepper together. Remove inherited shared setup. Set `AI_PROVIDER=mock`, leave `GEMINI_RESEARCH_MODEL` and `GEMINI_API_KEY` unset, enable durable quotas only against the new database, and keep both 008B flags off. If hosting variables and secrets cannot be changed without starting a new instance, keep traffic blocked until the platform confirms the exact environment on that instance.
5. **Rebuild staging frontend.** Set the three bound browser variables to the new staging services and keep the rollout flag off. Verify CORS and the generated browser requests, Auth redirects, private cache cleanup and approved deployment alias. Keep old builds containing production endpoints out of staging. Never roll back to a shared-project binding.
6. **Confirm isolation before reopening.** Compare frontend and backend project refs, verify own-account auth/history using synthetic identities, confirm requests and writes appear in staging only, and confirm there are no running staging processes with the old binding. Verify the production release and its routing remain unchanged using authorized platform records. Do not use a production database connection for this check.

## Activate ASK-CORE-008B after staging isolation

| Order | Required condition |
|---|---|
| 1 | Rehearse the migration offline and review the staging ledger/dry run. Apply migration `202611260001` to isolated staging only after separate approval. Verify service-role RPCs, ownership checks, restrictive policies, and schema visibility. |
| 2 | Deploy the compatible candidate backend with `SERVER_CHAT_TURNS_ENABLED=false` and `QUOTA_ENFORCEMENT_ENABLED=true`. Verify legacy authenticated and guest chat against staging. |
| 3 | Set staging Render `SERVER_CHAT_TURNS_ENABLED=true`, leaving the browser flag off. Smoke the new route with synthetic authenticated accounts and the existing mock chat provider. A disabled route is expected to return 404. |
| 4 | Build the staging frontend with `VITE_SERVER_CHAT_TURNS_ENABLED=true`. Verify new chat, history, ownership and recovery, then leave the rollout scoped to staging. The backend boolean defaults to false; the frontend flag defaults off and accepts the literal string `true`. Neither flag needs changing on production during staging UAT. |

Research is a separate approval boundary. Mock chat does not mock the real Deep Research provider factory. Initial staging can test reopening a completed synthetic report and SQL trigger behavior without live AI. Only after verifying staging project mappings and obtaining explicit paid-call approval, set an approved `GEMINI_RESEARCH_MODEL` and staging-only Gemini key. Keep a single staging backend instance for this exercise, monitor only new synthetic jobs, and unset the agent again to pause staging research. During that pause, verify the old process stopped before treating the worker as stopped. [Backend flag](../../../backend/app/api/routes/chat.py) · [Frontend flag](../../../src/components/askhype/AskHypeShell.tsx) · [Research dependency](../../../backend/app/api/dependencies.py)

## Staging UAT checklist

| Area | Synthetic test and acceptance |
|---|---|
| Topology and CORS | Check the deployed frontend bundle's API and Supabase hostnames. Verify allowed preflights from the canonical staging origin and rejection from an unapproved origin. Verify staging routes use `/api`, health responds, and production bindings are untouched. |
| Auth | Signup creates a free profile. Verify login, refresh, logout, recovery email link, expired token handling, independent guest identity and account A/B separation. Do not send to production recipients. |
| Legacy chat | Flag off, exercise guest and authenticated chat and existing history writes. Use mock chat for no-provider UAT and verify supported image upload handling. |
| Durable chat | Flag on, verify the server claims one user turn and persists one assistant row. Read the completed reply after reload, reconnect and browser close after confirmed persistence. A lost acknowledgment uses status recovery. A stopped backend may leave an unknown outcome. |
| Idempotency and quotas | Replay the same ID in parallel and after completion. Expect one reservation, no duplicate assistant row, no charge for GET, and conflict on changed input. Check old rolling-window limits 5/10/200 with synthetic accounts. Verify ownership denial and quota denial before execution. |
| Pagination and inherited history | Seed more than 30 threads and messages, including tied timestamps. Verify older pages, ordering, dedupe, refresh, deletion and reopening both legacy and new rows. Read account A then switch to B with a delayed A response. |
| Deep Research | Reopen a terminal synthetic linked report, validate ownership and inspect quota/worker evidence without live calls. If later approved, create one bounded synthetic job using staging Gemini only. Verify status transitions, single persisted result, and no additional user quota on polling. |
| Presentation V3 | Generate a synthetic deck with the mock planner. Download and reopen an editable PPTX, including a simple document-backed case where supported. Keep illustrations OFF for isolated UAT; paid planner/illustration smoke requires separate approval. |
| Private cache | Update an installed legacy service worker, verify the named legacy cache is removed, inspect static precache and private GET exclusion, then reload offline. Switch accounts and confirm prior history, usage and reports are absent. |
| Rollback | Disable frontend flag, validate old path and reading existing durable replies, allow status polling to drain, then disable the backend flag. Ensure staging remains pinned to staging and the private cache does not return. |

## Production migration rehearsal and rollback

1. **Rehearse locally and on isolated staging.** Run the disposable PostgreSQL harness below. Retain the exact application and migration revisions used for the successful run. Baseline the first five migrations, seed only synthetic fixtures, apply migration 6, and compare history, status, quota and research behavior with flags off and on.
2. **Production preflight is a separate approval.** Confirm restore capabilities and take a protected backup within production's approved backup boundary. Review the production migration ledger and schema shape through the approved operator workflow, including version drift, RLS, grants, table sizes, locks and historical records. Do not copy production data to staging. On an already migrated production project, the expected delta is only migration 6 after the first five versions are independently verified. Unexpected pending migrations, mismatched project identity or baseline drift stop the release.
3. **Release flags off first.** Apply the reviewed additive SQL in the approved window using the production-specific workflow. New indexes take normal schema/index locks; review lock time and maintenance impact. Verify migrations and health. Deploy the compatible backend and frontend with both flags off. Verify legacy chat/history and research on authorized test accounts before gradually enabling the backend, then the frontend. Keep the prior artifacts and environment mappings ready.
4. **Roll back behavior without dropping data.** Rebuild the frontend with its flag off and preserve 008A private-cache containment. Retain the backend status endpoint for existing in-flight clients until recovery drains where possible. Disable the backend flag or restore the previous backend artifact and settings. Keep existing conversation/assistant rows, the turn journal, deletion tombstones and RLS policies. Investigate unresolved claims; do not redispatch uncertain work. Use a separately reviewed forward migration for schema defects. Restore a backup only under a separate recovery decision, with an explicit plan for writes after the restore point. Staging rollback must retain staging-only bindings.

### Offline evidence

```bash
PG_BIN=/usr/lib/postgresql/17/bin bash backend/scripts/validate_chat_turns_postgres.sh
```

Both the fresh and upgrade runs passed locally on PostgreSQL 17 during ASK-ENV-001A. The harness uses a private Unix socket, applies the repository's six migrations to a fresh disposable DB and to a representative upgrade path with synthetic history, and verifies quota, ownership, settlement, cursor and linked-research compatibility. It does not represent Supabase managed Auth, PostgREST or actual hosted environment configuration. Those checks remain UAT gates. [Harness](../../../backend/scripts/validate_chat_turns_postgres.sh) · [008B implementation limits](../ask-core-008b/implementation-report.md)

## Actions requiring explicit approval

- Create the Supabase staging project, environments or provider/SMTP accounts. Obtain and configure credentials in the appropriate service.
- Change staging aliases, access controls, CORS, SMTP, runtime settings, deploys or replicas. Suspend any old staging service after proving it has no production role.
- Link a CLI to a hosted project, inspect hosted database schema/ledger, apply any hosted migration, or seed synthetic data in a hosted database.
- Test email delivery to external inboxes or run any live Gemini or Deep Research request. Reserve separate budget and project approval.
- Perform production backup/restore actions, configuration changes, migration, deployment, flag activation, or release rollback.

No external resource, live database connection, hosted migration, deployment, or provider call was made to prepare this plan.
