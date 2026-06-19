# ADR-006 — Model routing (cheap triage → premium) + caching + batch

> **Status:** Accepted
> **Date:** 2026-06-11
> **Deciders:** Architecture team
> **Related:** [ARCHITECTURE.md §7.5](../ARCHITECTURE.md) · [AI_SUBSYSTEM_SPEC.md §3, §7](../AI_SUBSYSTEM_SPEC.md) · [OBSERVABILITY.md §2.2](../OBSERVABILITY.md) · [ADR-009](./0009-configurable-ai-provider-adapter.md)

## Context

AI is the signature feature and the dominant variable cost. Exam season concentrates load: a single class generates 30 submissions, each with multiple questions, each a model call. Naively sending every call to the most capable model — synchronously, with no caching — would be both **slow** (interactive timeouts) and **expensive** (premium-tier tokens on tasks a cheap model handles fine), and would let one school's exam-season burst blow the cost budget for everyone ([PRD.md §10](../PRD.md), [ARCHITECTURE.md §1 P9](../ARCHITECTURE.md#1-architectural-goals--principles)).

The cost levers available are well understood: not every task needs the premium model; the answer key/rubric is identical across a whole class; and whole-class grading is rarely urgent.

## Decision

Control AI cost/performance with three composable levers, expressed as **provider-independent capabilities** (the adapter maps them to its SDK — [ADR-009](./0009-configurable-ai-provider-adapter.md)):

1. **Tiered model routing** ([AI_SUBSYSTEM_SPEC.md §3](../AI_SUBSYSTEM_SPEC.md)). The orchestrator routes by **tier** (`cheap`/`premium`), not model name. Cheap-tier handles OCR triage, blank-detection, clean-scan MCQ/short-answer; premium-tier handles generation, essay, and handwriting. Low-confidence cheap-tier triage **escalates** to premium. *(MiniMax adapter at MVP: both tiers use `MiniMax-M2.7`; the routing seam stays so a fast/large pair can be configured later.)*
2. **Prompt caching.** The stable prefix — **answer key + rubric** for grading, **source + config** for generation — is cached across all calls for an exam. A 30-question class reuses the prefix 30× (cache reads from MiniMax's `cache_read_input_tokens` accounting, typically ≈ 0.1× of base input cost).
3. **Async batch** for non-urgent whole-class grading (~50% cost on providers that support it). The worker batches when ≥10 ungraded, non-urgent submissions exist; interactive single submissions run live. *(MiniMax support TBD — verify in M3; degrade gracefully to per-item async calls if batch is unavailable.)*

Per-school **quotas** are enforced **above** the adapter, before dispatch — a hard cap returns a `quota_exceeded` job error; a soft cap (≥80%) raises a UI banner. Every job's tokens/cost/provider/model are metered to `ai_usage_record` ([OBSERVABILITY.md §11.2](../OBSERVABILITY.md#112-operational-ai-metrics)).

## Alternatives considered

- **Single premium model for everything, always synchronous** — rejected: cost and latency both untenable at exam-season scale.
- **Hardcoding specific model IDs in the orchestrator** — rejected: tier routing is provider-independent; model IDs are **config** so they can shift between releases and across providers without code change ([AI_SUBSYSTEM_SPEC.md §6](../AI_SUBSYSTEM_SPEC.md#6-tier-routing--cost-controls-prd-10)).
- **No per-school quota** — rejected: one school's burst would starve others and blow the budget; quotas are the fairness/cost backstop ([ARCHITECTURE.md §5.3](../ARCHITECTURE.md#53-noisy-neighbor--fairness)).

## Consequences

**Easier:**
- Cost scales sub-linearly with volume (caching + cheap tier + batch); per-school quotas cap blast radius.
- Tier/caching/batch are **capabilities, not provider specifics** — an adapter without one loses that saving but still works.

**Harder / must uphold:**
- Cache breakpoints must sit on the **last stable block** (key/rubric/config), never on volatile content (IDs/timestamps) — a misplaced breakpoint silently kills the cache hit ([AI_SUBSYSTEM_SPEC.md §2](../AI_SUBSYSTEM_SPEC.md#2-two-capabilities-four-task-types)).
- Escalation paths and batch fallbacks add orchestration branches; both runs of an escalation must be metered ([AI_SUBSYSTEM_SPEC.md §6](../AI_SUBSYSTEM_SPEC.md#6-tier-routing--cost-controls-prd-10)).
- Model IDs are config that **drifts** — confirm current IDs against provider docs before each release ([CLAUDE.md](../../CLAUDE.md)).
