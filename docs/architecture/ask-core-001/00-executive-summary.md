# ASK-CORE-001 · Executive summary

Audit baseline `7f5edc6` on 26 November 2026. Code references include the existing local grounding diagnostics where explicitly noted. Deployment details supplied in the brief are treated as operational context. Live routing, credentials, quotas, worker counts and post-replenishment recovery were outside the verification boundary.

## Product requirements

AskHype is one general-purpose multilingual assistant for knowledge, creative work, analysis and current information. Natural language expresses intent. The user never selects a provider, model or search strategy, and can continue the same conversation through a provider outage. Explicit controls remain for workflows that carry meaningful user choices, including asynchronous Deep Research and producing a downloadable file. The latest user request governs the answer and explicit language overrides. Relevant earlier turns resolve genuine references. Verified claims carry traceable evidence, and an inability to verify is stated clearly. Provider, model, cost and fallback are operational details.

## Highest-priority findings

1. **Grounding has separate routing, provider and evidence failures.** Offline classification shows a scores question triggers Search but “Who scored the goals?” does not. The prior live diagnostic using SDK 2.34.0 returned HTTP 402 on all three variants including the ungrounded control. That demonstrates a project-level blocker for the tested credential. Production project equivalence and Search-plus-JSON compatibility remain unverified. A successful response can also return zero usable sources. [Prompt lifecycle](02-prompt-lifecycle-audit.md) · [Provider matrix](05-provider-capability-matrix.md)
2. **Authenticated history is durable storage with browser-owned coordination.** The browser writes the user message and assistant response separately. A generation can succeed while the answer is missing on refresh, and private GET caching and auth transitions warrant urgent testing. These are code-backed mechanisms. The reported field incidents have no confirmed common cause. [History audit](04-conversation-and-history-audit.md)
3. **Shared Supabase creates an environment boundary problem.** If both environments run with research and durable quota enabled, each app process can scan the same active jobs. Compare-and-set and the result trigger protect persistence, while provider polls can still race. Separate projects and credentials are the preferred isolation. [History audit](04-conversation-and-history-audit.md)
4. **Ordinary chat already has its own general-purpose system prompt.** The legacy Hype rules are still active on the specialized path, and current-message keywords can select that path before other tools. Keep the Hype evidence boundary, simplify ordinary prompt assembly and preserve specialized services. [Rules inventory](03-legacy-rules-inventory.md)
5. **Adding SDKs alone will leave the reliability gap.** Chat needs a canonical turn, explicit evidence requirements, one execution budget and structured attempt accounting before automatic cross-provider failover. [Target architecture](06-target-architecture.md)

## Decision and next task

Start with **ASK-CORE-008A, History incident instrumentation and private-cache containment**. Reproduce refresh, auth change, failed write and cross-tab cases with synthetic accounts in isolation. Separate private GET traffic from the PWA cache, purge the legacy private cache safely, and add content-free persistence diagnostics. This addresses a shared dependency of every provider without redesigning chat. In parallel, verify the production Gemini project and worker topology through authorized operational review. Stage capability-aware fallback only after history, evidence and budget gates pass.

The minimum stabilization release is smaller than AI Core V2. Keep the current API and Gemini path, protect account history, expose failure categories and billing alerts, and make current-information failures explicit. Preserve Presentation V3 and Deep Research. [Migration plan](08-migration-plan.md) · [Delivery backlog](09-prioritized-backlog.md)
