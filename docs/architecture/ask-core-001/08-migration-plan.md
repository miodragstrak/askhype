# Incremental migration plan

## Minimum viable stabilization release

1. **Reproduce and contain history risk.** Add content-free diagnostics and synthetic browser/SQL fault tests. Scope the PWA cache to public assets, purge legacy private entries during SW upgrade, and gate history rendering and in-flight handlers by owner/epoch. Preserve existing storage and UI workflows.
2. **Separate operational environments.** Verify project and credential mappings for browser, backend, worker and provider. Move staging to its own Supabase and provider projects with isolated auth callbacks, quotas and synthetic data. Until then, constrain reconciliation to one authorized owner with a reversible explicit worker switch. Verify all relevant migrations and backup/restore using disposable data.
3. **Make failures actionable.** Review the preserved safe diagnostics for release, add monitoring for provider billing, Search evidence and persistence outcomes, and verify the production Gemini relationship. After separate approval rerun only the bounded live grounding diagnostic. Keep current evidence fail-closed and current quota semantics.

This release can ship through normal approval without a new AI vendor, UI model selector, broad classifier rewrite or presentation/research redesign.

## V2 stages and rollback

| Stage | Entry and rollout | Exit / rollback |
|---|---|---|
| Evaluation baseline | Build independent fixtures, fault injection and blind review before prompt or provider tuning. Use the existing paths as baseline. | Publish dated metrics and release gates. Roll back evaluation infrastructure independently. |
| Conversation and prompt boundary | Extract canonical turn/context builder and test native roles with Gemini behind a server-controlled cohort flag. Start with the existing envelope and preserve old stored response shapes. | Held-out context and language gates. Flip prompt flag back on quality regression. |
| Application-owned account history | Introduce compatible read API/sequence and idempotent turn settlement in a separately reviewed migration if necessary. Read historical rows through projection. Cut over one writer per cohort, with explicit reconciliation at the seam. | Verify same-account refresh/retry/delete and RLS at volume. Revert traffic flags with reverse-readable writes. Retain additive schema and buffers until settled. |
| Response normalization and evidence | Wrap Gemini in the normalized contract. Evaluate native text and citations for ordinary grounded chat if the diagnostic supports it. Keep typed specialty adapters. | Require safe degradation and source quality gates. Disable native text adapter or evidence routing flag while preserving the existing limitation. |
| Alternate providers | Add one adapter at a time, credentials in separate projects. Start with replay/fault fixtures and a small staging cohort. Live comparison and cross-provider private file processing each require authorization. | Measure real capability, cost and privacy limits. Remove a provider from capability registry to roll back. |
| Gateway and rollout | Enable ordered single fallback behind a disabled-by-default server flag. Apply cost/deadline caps before exposure. Canary using isolated staging, then production cohort with verified alerting and rollback. Streaming is later. | Roll back fallback, evidence and context flags independently, then restore prior artifact if needed. Keep provider attribution and persisted turns readable throughout. |

## Risks and alternatives

- Browser-only history is inexpensive and appropriate for guests, but it cannot provide authoritative account turn settlement across tabs and retries. Reuse existing Postgres tables where possible; service-owned writes require policy review.
- Provider-hosted conversation IDs simplify one adapter and couple history to that provider and its retention rules. Keep application-owned data canonical and provider IDs optional.
- Keep deterministic explicit-mode rules and evidence safety gating. A pure regex router misses multi-turn intent; an extra LLM classifier on every request adds cost and latency. Test native tool choice within a bounded allowlist and one model call first.
- Keep vendor-native Search initially. A shared independent search backend may improve consistency but adds another provider, operational cost and retrieval governance. Revisit only if evidence or availability data justify it.
- A large rewrite introduces risk to working research and presentations. Independent flags, persisted compatibility and sequential adapter rollout allow narrower rollback.
- A higher infrastructure timeout cannot solve provider-side rejection. Measure the shortest app/proxy/client deadline and account for cost, privacy and idempotency before adding fallback or streaming.

Operator preconditions include authorized access to deployment and provider metadata, explicit paid test approval, availability of synthetic accounts and separate Supabase, documented retention/DPA requirements, baseline SLOs and a prior known-good artifact. No production changes are part of this audit.
