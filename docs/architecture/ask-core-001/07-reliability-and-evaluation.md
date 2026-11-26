# Reliability controls and independent evaluation

## Evidence policy

Separate evidence **requirement**, **tool invocation**, **provider evidence returned**, and **answer actually supported**. Preserve provider-native citation spans and source IDs. Validate that spans refer to the delivered text, source references are unique and resolvable, URLs are safe, and untrusted tool/page content stays data. For time-sensitive questions check available dates, entity/place, and source type against the resolved request. Reject obvious future/past mismatches, unrelated citations, and unsupported statements framed as verified. Unknown source dates are unknown, and a search timestamp alone does not establish publication or event time. Use vetted authorities for high-risk topics where available, and distinguish sourced statements, synthesis and limitations. A small count of syntactically valid links alone proves no claim. For uncertain relevance, cite only what can be supported or give a clear limitation. Establish baseline tests with frozen evidence snapshots and no additional model verification call. Deep Research, public URLs and document inputs retain their own validators. [Current extractor](../../../backend/app/providers/gemini.py#L842) · [Hype evidence rules](../../../backend/app/prompts/askhype.py#L89)

Native text with citations is the default experiment for ordinary grounded chat once the live diagnostic is authorized. The app can still map output into its existing `ChatResponse`. Keep structured output for contracts where its benefit is demonstrated, including XLSX, PPTX and validated tool arguments. If plain Search and schema variants both hit provider errors, diagnose status and project entitlement first. Previous HTTP 402 affected A, B and C on the tested project. Replenishment is reported, and recovery and production credential equivalence are unverified. [Probe](../../../backend/scripts/gemini_grounding_probe.py) · [Google billing](https://ai.google.dev/gemini-api/docs/billing#prepay)

## Operational controls

| Signal | Available now | Proposed action |
|---|---|---|
| User quota | Durable prompt reserves/finalizes and plan windows; research and animation use distinct limits. Existing SQL tests are available. | Alert on stale reserves, lost finalizations and duplicate logical turns. Track provider attempts separately from user quota. |
| Provider / billing | Same-vendor retry/fallback and partial logs. Local diagnostics add actual attempted model, status, source counts and correlation. No central spend ledger found in the runtime paths reviewed. | Alert immediately on billing/auth/capability denial; reconcile provider-reported and invoiced usage. Configure per-attempt, per-turn and daily project caps and budget warning/headroom thresholds. |
| Latency / quality | Health route and service logs; presentation runner reports planning and artwork stages offline. Research lifecycle has status and age. | Emit queue, provider, evidence, persistence, total latency and time-to-first-output histograms. Correlate by generated turn ID. Track grounded success and limitations separately. |
| Persistence | UI notices on history failures; research emits lifecycle events and worker scan errors. | Track hydrate failures, incomplete turns, read-after-write and duplicate/lease conflicts. Alert on no successful scans, oldest queued job breaching SLO, or unexpected jobs crossing environments. |
| Configuration | Safe production startup rules, explicit origins, diagnostic timeout settings. | Record redacted release ID, dependency/adapter version, project alias and worker eligibility. Keep rollout gates and budgets operator-controlled with reversible defaults. |

Record outcome and latency by environment, route, capability, provider and model. Keep tokens, model requests and Search calls as separate metrics. Unknown usage stays unknown and is reconciled separately. Never log content, credentials, attached bytes or full upstream errors. Some existing non-grounded SDK error paths use `exc_info=True`; audit redaction before broadly enabling gateway logs. No user identifiers in metric labels. [Existing error logger](../../../backend/app/providers/gemini.py#L1106) · [Research events](../../../backend/app/services/research_service.py#L27) · [Presentation evaluator](../../../backend/scripts/presentation_eval.py)

## Existing test evidence

- **Unit and mock provider.** Backend covers classification, Gemini request shapes, safety and fallback, document validation, research statuses, rendering and quota arithmetic. Frontend Vitest covers selected state helpers, repository/import and research UX. Passing mocks establish deterministic behavior and contracts. [Grounding tests](../../../backend/tests/test_chat_grounding.py) · [Identity/usage tests](../../../backend/tests/test_identity_usage.py) · [Frontend repository tests](../../../src/services/conversation-repository.test.ts)
- **Integration.** ASGI route tests exercise dependencies with mocked services. A disposable PostgreSQL script exercises real migration and research lifecycle/RLS behavior separately. This audit did not execute the PostgreSQL harness or an authenticated browser E2E. [Chat tests](../../../backend/tests/test_chat.py) · [PostgreSQL harness](../../../backend/scripts/validate_research_postgres.sh)
- **Live and smoke.** There are opt-in Gemini diagnostic/evaluation tools and prior live observations. CI has no provider/model quality or multi-account browser regression gate. An endpoint smoke establishes deployability, and a held-out execution suite evaluates actual conversational quality. [CI](../../../.github/workflows/ci.yml) · [Probe](../../../backend/scripts/gemini_grounding_probe.py) · [Presentation QA](../../../backend/scripts/presentation_qa.py)
- **Audit run.** Local backend pytest reported 631 passed and one opt-in video integration skip with the preserved diagnostic patch. Frontend Vitest reported 35 passed. The deterministic checks reproduced cases A–D and the mixed factual writing gap. No provider, database or deployment smoke ran during this audit.

## Independent 120-scenario design

Store fixtures with scenario ID, turns, language/script, user profile defaults, expected route/evidence, authoritative frozen evidence, required and forbidden claims, measurable assertions, and a human rating rubric. Every row below contains ten scenarios. Hold out three per row with different entities, phrasing and distractors. That gives 90 development and 30 held-out cases. Keep holdouts under independent review and version the fixtures and release reports. Do not tune on the holdouts.

| Ten scenarios per family | Coverage variations |
|---|---|
| Knowledge and reasoning | General, technical, mathematical and business questions, multi-step accuracy, false premise, explicit output length. |
| Writing and transformations | Creative, rewrite, translation with relevant prior answer, mixed fresh-facts writing, quoted instructions and formatting. |
| Current facts | News, weather, sports, travel, market/officeholder and schedule questions, date zone, relative date, sparse evidence. |
| Search and citation integrity | Explicit web, public URLs, good citations, bad span, mismatched city/date, duplicates, inaccessible URL, empty metadata. |
| Continuity | Scores→scorers, clarification, user correction, references beyond recent window, repeated retry, prior research result. |
| Topic switch and ambiguity | Football→Belgrade weather, ambiguous forecast, changed place, new topic vs same referent, obsolete window preferences. |
| Multilingual | Serbian Latin/Cyrillic, English, German, regional examples, translation, explicit override, mixed-language clarification. |
| Attachments and document safety | Image observations, file-backed facts, prior file absent, unsupported inputs, malicious text in evidence, attachment consent on fallback. |
| Specialized routing | Hype, document, XLSX, Presentation V3 with native fallback, Deep Research persistence, false positive specialty activation. |
| History and authorization | Refresh, slow hydrate, two accounts, sign-out, tabs, token expiry, cache upgrade, concurrent turns/deletion, RLS and ownership. |
| Availability and fallback | 402, 429, 503, timeout, ambiguous dispatch, unsupported tool, refusal, pre/post-first-output disconnect, partial recovery. |
| Quota, latency and cost | Duplicate key, failed finalization, resend, tool cap, global/per-turn limit, concurrent reservations, deadline and known/unknown usage. |

Run deterministic contract and fault fixtures on every PR. Run browser and disposable PostgreSQL isolation in CI or a release lane. Run sandbox/staging live comparisons only with separate approval, a fixed budget and a baseline. Use a blind bilingual reviewer for relevance, clarity and context and evidence judgments. Use trusted snapshots for repeatable scoring and dated fresh facts only in the authorized smoke lane.

### Proposed initial release gates

- Zero cross-account reads/writes, unauthorized tool or attachment transfers, fabricated citation links, and duplicate final responses or quota reservations in critical fault cases.
- At least 90% of held-out cases pass the relevant human intent/context/language rubric, and no critical scenario fails. Use explicit clarification where needed rather than silently inventing context.
- At least 95% correct citation-to-claim alignment in evidence-eligible cases with zero grounded-success labels when usable evidence is missing. Score source availability and claim support independently.
- 100% of mock attempts stay within per-turn cap, preserve required evidence on fallback and finalize or recover the turn. Emit safe telemetry for every attempt.
- Establish staging p95 baseline separately for ordinary and grounded chat. Initial proposed p95 targets are 8 s and 20 s respectively on the approved profile, with zero over the configured end-to-end deadline. Fallback must meet the same hard ceiling. Release only within a preapproved measured per-turn and daily budget. Adjust SLO targets against data before enforcing a numerical release gate.
