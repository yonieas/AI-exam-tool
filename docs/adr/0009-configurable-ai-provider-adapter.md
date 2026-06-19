# ADR-009 — AI provider is a configurable adapter; MiniMax is the default

> **Status:** Accepted
> **Date:** 2026-06-18
> **Deciders:** Architecture team
> **Related:** [ARCHITECTURE.md §7.1](../ARCHITECTURE.md#71-provider-adapter-adr-009) · [AI_SUBSYSTEM_SPEC.md §2](../AI_SUBSYSTEM_SPEC.md#2-the-aiprovider-port-adr-009) · [BACKEND_CONVENTIONS.md §10](../BACKEND_CONVENTIONS.md#10-configuration--secrets) · [DEPLOYMENT.md §3](../DEPLOYMENT.md#3-environment-variables-env) · [ADR-004](./0004-structured-output-only-ai.md), [ADR-006](./0006-ai-model-routing-caching-batch.md)

## Context

The AI subsystem is the product's differentiator and depends on a capable multimodal + structured-output model. **MiniMax** (via its OpenAI-compatible API at `https://api.minimax.io/v1`) meets the capability requirements: text + image generation, JSON-structured output, prompt caching (`cache_creation_input_tokens` / `cache_read_input_tokens` in the usage payload). The MiniMax API also exposes an Anthropic-SDK-compatible endpoint, but we standardize on the **OpenAI-compatible path** because (a) image input via `image_url` content blocks is well-documented there, and (b) the `openai>=1.0` Python SDK is a stable, widely-used client.

Building the orchestration *directly* against the MiniMax SDK call would still create **vendor lock-in** that bites later:

- **Cost / compliance fallback** — a second provider as a cost lever or a procurement requirement.
- **Resilience** — a provider outage shouldn't be unrecoverable (though MVP degrades to manual grading — [PRD.md FR-G.7](../PRD.md)).

Retrofitting an abstraction after the orchestration, schemas, persistence, and safety code are all SDK-shaped is expensive; adding the seam **up front** is cheap.

## Decision

The FastAPI monolith's `ai/` module depends on a narrow **`AIProvider` port** — an interface defining the capabilities the exam subsystem needs, not a vendor SDK ([AI_SUBSYSTEM_SPEC.md §2](../AI_SUBSYSTEM_SPEC.md#2-the-aiprovider-port-adr-009)). Each provider ships an **adapter** implementing that port; the active adapter is chosen by **configuration** (`AI_PROVIDER` env, default `minimax`).

- **MiniMax is the default and the *only* adapter shipped in MVP.** The port exists so a second provider (OpenAI, Anthropic, Bedrock, Vertex, self-hosted) can be certified later **without touching** orchestration, JSON schemas, persistence, or safety gates — only the adapter changes.
- The port's capability contract includes **eligibility gates** (from [ADR-004](./0004-structured-output-only-ai.md)): forced structured output + untrusted-content isolation. A provider that can't do both is **not adopted**. Vision/PDF/caching are per-task-type gates.
- The adapter exposes a **normalized error surface** (`refusal`, `quota_exceeded`, `rate_limited`, `schema_invalid_after_retry`, `transient`) so orchestration stays provider-independent; raw provider error codes never leak past the adapter.
- **Model IDs are config, not hardcoded** — the MiniMax adapter maps `premium → MiniMax-M2.7`, `cheap → MiniMax-M2.7` (same model for both tiers at MVP; the tier-routing logic stays in place so a fast/large pair can be dropped in via config later) ([ADR-006](./0006-ai-model-routing-caching-batch.md)).
- The **provider key lives only in the API/worker environment** ([BACKEND_CONVENTIONS.md §10](../BACKEND_CONVENTIONS.md#10-configuration--secrets), [DEPLOYMENT.md §3](../DEPLOYMENT.md#3-environment-variables-env)); the web frontend never holds it. Adding a provider adds a secret to the API/worker, nothing else.
- **Certification:** a candidate adapter must pass the **eval harness** golden sets at parity before it ships ([AI_SUBSYSTEM_SPEC.md §8](../AI_SUBSYSTEM_SPEC.md#8-eval-harness-prd-7)). Golden-set runs are tagged by `ai_provider` for cross-provider comparison.

## Alternatives considered

- **Direct MiniMax SDK coupling, abstract later if needed** — rejected: the seam is cheap up front and expensive to retrofit; the orchestration/schema/safety code would all need rework.
- **Anthropic-SDK-compatible path of MiniMax's API** — rejected: image input (`image_url`) is better-documented on the OpenAI path, and the OpenAI Python SDK has wider ecosystem support (tooling, retry helpers, tracing integrations).
- **Multi-provider live router in MVP** (per-school/cost/automatic failover) — rejected for MVP scope: adds routing complexity before a second provider even exists. MVP = single active provider, config-time selection.
- **Lowest-common-denominator interface** that assumes no structured output / no vision — rejected: those capabilities are non-negotiable ([ADR-004](./0004-structured-output-only-ai.md)); the port requires them as eligibility gates rather than designing down to a weaker provider.

## Consequences

**Easier:**
- No vendor lock-in: a second provider = a new adapter + tier→model config + eval certification, with **zero** change to orchestration, schemas, persistence, or safety gates.
- The API contract, schemas, and UI **never name a vendor** — the provider is invisible above the adapter.
- Per-provider cost/accuracy is comparable via the `ai_provider` tag on AI jobs.

**Harder / must uphold:**
- The orchestration must be written against the **port**, never the SDK — leaking MiniMax specifics above the adapter defeats the ADR.
- Schemas and safety gates live **above** the adapter and stay provider-independent ([ADR-004](./0004-structured-output-only-ai.md)).
- **Open question:** which second provider to certify first. This becomes its own ADR when resolved.