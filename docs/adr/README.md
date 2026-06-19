# Architecture Decision Records — Teacher AI Exam Tool

> **What this is:** the full text of the architecture decisions summarized in [ARCHITECTURE.md §14](../ARCHITECTURE.md#14-architecture-decision-records). That table is the index; these files are the rationale, alternatives, and consequences behind each load-bearing decision.

An **Architecture Decision Record (ADR)** captures a single significant decision: the context that forced it, the choice made, the options rejected, and the consequences accepted. ADRs are **immutable once Accepted** — we don't edit a decision, we supersede it with a new ADR that references the old one.

## Format

Each ADR follows the [Michael Nygard format](https://github.com/joelparkerhenderson/architecture-decision-record):

- **Status** — Proposed / Accepted / Superseded (by ADR-NNN) / Deprecated
- **Context** — the forces at play; why a decision was needed
- **Decision** — what we chose, stated plainly
- **Alternatives considered** — what we rejected and why
- **Consequences** — what becomes easier, what becomes harder, what we must now uphold

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](./0001-modular-monolith-with-separate-services.md) | Single-process FastAPI monolith with in-process AI adapter; BullMQ for async | Accepted |
| [ADR-003](./0003-transactional-outbox.md) | Transactional outbox for events | Accepted |
| [ADR-004](./0004-structured-output-only-ai.md) | Structured-output-only AI (no tools, no secrets in context) | Accepted |
| [ADR-005](./0005-human-in-the-loop-ai-grades.md) | Confidence + flag-for-review gate on AI grades | Accepted |
| [ADR-006](./0006-ai-model-routing-caching-batch.md) | Tiered model routing (Haiku → Opus) + prompt caching | Accepted |
| [ADR-007](./0007-uuid-v7-primary-keys.md) | UUID v7 primary keys | Accepted |
| [ADR-009](./0009-configurable-ai-provider-adapter.md) | AI provider is a configurable adapter; MiniMax is the default | Accepted |

**Deleted / superseded:**
- ADR-002 (pooled multi-tenancy with RLS) — multi-tenancy removed; replaced by application-layer `owner_id` scoping.
- ADR-008 (separate school-fee and SaaS billing) — finance billing removed.
- ADR-010 (Indonesian fee gateway) — finance billing removed.

## Proposing a new ADR

1. Copy the format above; number it `NNNN-kebab-title.md` (next free number).
2. Open it as **Proposed**; circulate for review.
3. On acceptance, set **Accepted** + the date, and add a row to the index here **and** to [ARCHITECTURE.md §14](../ARCHITECTURE.md#14-architecture-decision-records).
4. To reverse a prior decision, write a new ADR that **supersedes** it — don't rewrite history.