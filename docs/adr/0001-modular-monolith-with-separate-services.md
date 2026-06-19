# ADR-001 — Single-process FastAPI monolith with in-process AI adapter; BullMQ for async

> **Status:** Accepted
> **Date:** 2026-06-18
> **Deciders:** Architecture team
> **Related:** [ARCHITECTURE.md §3, §6, §7](../ARCHITECTURE.md) · [BACKEND_CONVENTIONS.md §1](../BACKEND_CONVENTIONS.md#1-module-layout) · [AI_SUBSYSTEM_SPEC.md §1](../AI_SUBSYSTEM_SPEC.md) · [ADR-004](./0004-structured-output-only-ai.md), [ADR-009](./0009-configurable-ai-provider-adapter.md)

## Context

The product ([PRD.md](../PRD.md)) is a focused single-teacher tool: Google login, AI exam generation, AI grading. The scope is small enough that splitting into separate services (per the original ScholarX architecture) would add operational overhead without proportional benefit. At the same time, the user's stated constraint is **"modular monolith for easy to add features in the future"** — meaning future flexibility matters more than peak theoretical throughput.

The AI subsystem is the largest workload (Python ecosystem for vision/PDF/structured output), but the volume is bounded (one teacher, bursty). It does not warrant a separate deployable service at MVP.

## Decision

Build the **entire backend as a single FastAPI monolith** with clear module boundaries (one module per ERD subdomain). The **AI adapter runs in-process** inside the monolith — no separate Python AI service. Heavy work (generation, grading) is dispatched through **BullMQ on Redis** and consumed by a separate `ai-worker` process (same image, different command) that also calls the AI adapter in-process.

- **Modules** ([BACKEND_CONVENTIONS.md §1](../BACKEND_CONVENTIONS.md#1-module-layout)): `auth`, `subjects`, `classes`, `students`, `exams`, `questions`, `grading`, `files`, `ai`.
- **Cross-module interaction** is via injected services only; modules never read another module's tables directly.
- **The AI adapter port ([ADR-009](./0009-configurable-ai-provider-adapter.md))** lives inside the `ai/` module; only the `ai-worker` and the synchronous paths call it.
- **Module seams stay clean** so a future hotspot can be extracted to a separate process without rewrite.

## Alternatives considered

- **Separate Python AI service (the original ScholarX design)** — rejected at this scope: the boundary cost (HTTP dispatch, auth, deployment) outweighs the benefit (independent scaling) at single-teacher volume. Preserved the abstraction (the `AIProvider` port) so future extraction is mechanical.
- **Full microservices from the start** — rejected: contradicts the user's monolith constraint; premature decomposition.
- **Single process for everything (no `ai-worker`)** — considered: would simplify, but long-running AI tasks would block the API event loop. The worker process is a cheap mitigation.

## Consequences

**Easier:**
- One codebase, one deployable, one Dockerfile.
- Local development is `docker compose up` — Postgres + Redis + MinIO + api + ai-worker + web.
- Future extraction of the AI module to a separate service is a directory move + transport swap, not a rewrite.

**Harder / must uphold:**
- Module discipline is **enforced, not optional** — a module reaching into another module's tables is a review failure. The boundary is social + lint, not physical.
- The API event loop must never call a long-running AI call synchronously — all generation/grading goes through BullMQ. A linter check enforces this on `ai_provider.generate_structured` callsites.
- In-process AI means the API container has the `MINIMAX_API_KEY` env var; we mitigate by scoping the env to the API and worker images only (not the web).