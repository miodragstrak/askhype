# Staging configuration and Supabase bootstrap

All values below are public constants, repository defaults or placeholders. Obtain staging secrets from approved managers when executing. Never put a database password, Supabase secret key, Gemini key, guest pepper or SMTP credentials in Vercel browser variables.

## Vercel browser build environment

| Name | Initial isolated staging value and behavior |
|---|---|
| `VITE_API_BASE_URL` | Verified dedicated staging Render origin, without `/api`. Browser helpers append `/api/…`. Default is localhost for development. |
| `VITE_SUPABASE_URL` | New staging project API origin. Required. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Matching staging publishable key. Required and intentionally public. |
| `VITE_SERVER_CHAT_TURNS_ENABLED` | `false` or unset initially. The candidate enables server-owned turns for authenticated ordinary chat only when the literal string is `true`. |
| `import.meta.env.DEV` | Vite built-in. A production build sets it false; it is not a project setting. |

Update only the verified staging deployment scope. An existing Vite bundle keeps its old values until rebuilt. Check the new bundle's request hostnames using a clean browser profile. The production alias must remain bound to its current deployment. [Vercel environment variables](https://vercel.com/docs/environment-variables)

## Render backend runtime environment

| Names | Repository defaults / isolated staging action |
|---|---|
| `APP_NAME`, `APP_ENV`, `API_PREFIX`, `PORT` | `AskHype API`, `staging` explicitly, `/api`, and Render's service port. Docker default is 8000. Keep `/api` to match clients and health check. |
| `FRONTEND_ORIGIN`, `FRONTEND_ORIGINS` | Set `FRONTEND_ORIGIN` to the exact canonical staging frontend origin. A comma-separated `FRONTEND_ORIGINS` is optional and unioned with it. Remove inherited production or localhost entries from this staging service. No wildcard; CORS credentials are enabled. |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `ANONYMOUS_ID_PEPPER` | New staging API origin, matching privileged staging key, independently generated staging pepper. Required for durable staging usage. Put the sensitive values on Render only. |
| `QUOTA_ENFORCEMENT_ENABLED`, `ANONYMOUS_PROMPT_LIMIT`, `FREE_ROLLING_24H_PROMPT_LIMIT`, `PREMIUM_ROLLING_24H_PROMPT_LIMIT` | Set `true` after staging DB bootstrap, with 5, 10, 200 respectively. The authenticated quota RPC also enforces 10/200 on the DB side. Legacy aliases `FREE_MONTHLY_PROMPT_LIMIT` and `PREMIUM_MONTHLY_PROMPT_LIMIT` are accepted by settings; omit those aliases in new staging. |
| `MOCK_SUBSCRIPTIONS_ENABLED`, `SERVER_CHAT_TURNS_ENABLED` | Set both `false` initially. Mock subscriptions default on in development, and server turns default off; the new server routes require durable quotas in addition to their flag. A synthetic premium fixture can be seeded by an authorized staging administrator. |
| `AI_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` | Initially `mock`, no key, configured default `gemini-3.5-flash-lite` unused, and omit the optional fallback. Separately approve real-provider UAT before setting `gemini` and the dedicated staging credential. |
| `GEMINI_TIMEOUT_SECONDS`, `GEMINI_TEMPERATURE`, `GEMINI_MAX_OUTPUT_TOKENS` | Defaults 45, 0.4 and 4096. Preserve these unless an approved diagnostic requires an override. |
| `GEMINI_PRESENTATION_MODEL`, `GEMINI_PRESENTATION_MAX_OUTPUT_TOKENS`, `GEMINI_PRESENTATION_TIMEOUT_SECONDS`, `GEMINI_PRESENTATION_THINKING_LEVEL` | Optional. Baseline planning inherits general settings where unset. Match the approved presentation release profile when testing live. Leave thinking override unset unless the model combination was verified. |
| `PRESENTATION_ILLUSTRATION_MODE`, `PRESENTATION_ILLUSTRATION_TIMEOUT_SECONDS`, `GEMINI_PRESENTATION_IMAGE_MODEL` | Start `OFF`; default deadline 18 and configured default image model `gemini-3.1-flash-lite-image`. Separate paid UAT is required for COVER/ENHANCED. |
| `GEMINI_RESEARCH_MODEL`, `RESEARCH_DAILY_LIMIT`, `RESEARCH_MAX_DEPTH` | **Remove/unset the model** for initial and cutover stages. Keep limit 3 and maximum depth `standard`. A non-empty model with durable quotas starts an in-process reconciler. An approved staging agent later requires a separate staging credential and worker verification. |
| `GEMINI_ANIMATION_MODEL`, `ANIMATION_DAILY_LIMIT`, `ANIMATION_MP4_POC_ENABLED`, `GENERATIVE_SVG_BETA_ENABLED`, `ANIMATION_RENDER_TIMEOUT_SECONDS` | Omit the chat-model override unless needed, use default 10 daily, set both flags `false`, keep timeout 100. Animation is outside 008B UAT. |

The inventory comes from executable settings and current browser reads. `APP_ENV=staging` skips the production-only validation block, so the operator must verify the explicit bindings. No `DATABASE_URL` is used in the app path. CLI database access, Supabase auth policy, dashboard SMTP configuration and platform-managed metadata are separate. Check inherited Render environment groups for references to production secrets, including older revisions and background services. [Runtime settings](../../../backend/app/core/config.py) · [Backend example](../../../backend/.env.example) · [Render environment configuration](https://render.com/docs/configure-environment-variables)

## Bootstrap procedure after approval

1. Create a new managed Supabase project dedicated to staging. Record project ref, region, and ownership in the approved operator record. Confirm staging and production refs are distinct. Use a staging-only administrative session and CI secret scope. Use a throwaway checkout or work directory with fresh CLI linkage. The current repository has a local `supabase/.temp/` directory, and its target was intentionally not inspected. Do not reuse its link state.
2. In the new project, enable the Auth email/password flow used by the app and set the **Site URL** to the canonical staging frontend origin, such as `https://askhype.vercel.app` only once that alias is confirmed isolated. Signup supplies no redirect override and therefore needs the correct Site URL. Add the exact `<staging-origin>/reset-password` URL to the redirect allowlist. Password recovery builds it from `window.location.origin`. Use the exact staging root if the confirmation template uses it. Avoid wildcard preview redirects and production callback URLs. Keep the SPA rewrite for direct navigation to `/reset-password`. [Signup](../../../src/auth/AuthContext.tsx) · [Recovery](../../../src/pages/ForgotPasswordPage.tsx) · [Supabase redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
3. Obtain the staging publishable key for the browser and the matching staging secret key for the Render backend. The backend key must be authorized for the required `service_role` path. Check Auth/JWT validation and Data API access to `public` with synthetic users during UAT. For email delivery, use approved test inboxes and a staging SMTP sandbox or allowlisted recipients. Supabase's default sender has delivery restrictions, so seeded confirmed users alone do not verify password-recovery delivery. [API keys](https://supabase.com/docs/guides/getting-started/api-keys) · [SMTP setup](https://supabase.com/docs/guides/auth/auth-smtp)
4. Managed Supabase supplies `auth.users`, `auth.uid()` and the database roles. Do not deploy local test auth shims to Supabase. From the freshly linked **staging-only** checkout, review `supabase migration list` and `supabase db push --dry-run` against the independently confirmed staging ref before a separately approved apply. Bootstrap the first five at the baseline release. Apply the sixth only once staging isolation and the migration rehearsal are approved. Validate ledger versions and the Data API schema cache before enabling the new backend endpoint. [Supabase migration workflow](https://supabase.com/docs/guides/deployment/database-migrations)
5. Seed with synthetic data after baseline setup. Keep an owner A and owner B with separate staging-only inboxes and credentials. Test guest in a clean browser profile and use an optional synthetic premium account with a supported profile plan update confined to staging. Use original synthetic threads, tied timestamps for pagination, harmless sample files, and quota rows owned by synthetic users as needed. For mock-only Research history, use an explicitly terminal synthetic result fixture and no provider job polling. Verify signup/profile triggering and account isolation. No production users, tokens, profiles, chat, research, quota/usage exports, file bytes, or backups are needed.

### Complete migration order

| Order | Checked-in file | Introduces |
|---|---|---|
| 1 | [202609190001_hype_ask_002_rolling_quotas.sql](../../../supabase/migrations/202609190001_hype_ask_002_rolling_quotas.sql) | Profiles, signup trigger, quota ledger, quota RPCs and grants/RLS. |
| 2 | [202611130001_ask_dr_001_research_jobs.sql](../../../supabase/migrations/202611130001_ask_dr_001_research_jobs.sql) | Research jobs and reservation RPC. |
| 3 | [202611130002_ask_anim_001_animation_quota.sql](../../../supabase/migrations/202611130002_ask_anim_001_animation_quota.sql) | Separate animation quota ledger and RPCs. |
| 4 | [202611220001_ask_p0_history_conversations.sql](../../../supabase/migrations/202611220001_ask_p0_history_conversations.sql) | Conversation tables, ownership FK, RLS and grants. |
| 5 | [202611250001_research_conversation_lifecycle.sql](../../../supabase/migrations/202611250001_research_conversation_lifecycle.sql) | Research linkage, indexes and atomic result trigger. |
| 6 | [202611260001_ask_core_008b_chat_turns.sql](../../../supabase/migrations/202611260001_ask_core_008b_chat_turns.sql) | Turn journal, deletion tombstones, pagination indexes, restrictive message policies and private RPCs. Apply after staging isolation. |

Do not use production as a schema source. The files above and managed Supabase primitives are sufficient for the documented application schema. Deploying the current baseline artifact may require selecting a version-controlled checkout without migration 6 for the first staging migration batch.
