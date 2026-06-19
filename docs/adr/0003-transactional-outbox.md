# ADR-003 — Transactional outbox for events

> **Status:** Accepted (inherited; not strictly required at MVP)
> **Date:** 2026-06-18
> **Deciders:** Architecture team
> **Related:** [ARCHITECTURE.md §6](../ARCHITECTURE.md) · [BACKEND_CONVENTIONS.md §6](../BACKEND_CONVENTIONS.md#6-errors)

## Context

State changes that must notify other modules or external consumers (an exam is published, a grading run is finalized, an AI grade is overridden) face the same **dual-write** problem in any service architecture: write the domain row to Postgres **and** publish to the bus in the same handler, and a crash between them leaves the system inconsistent (an event for a rolled-back change, or a committed change no consumer ever hears about).

The pattern is preserved from the original architecture and remains the recommended shape for any cross-module notification we add later, but at MVP the only async pipeline is **AI jobs via BullMQ** — which is in-process and idempotent, so the outbox is not strictly required yet. We adopt this ADR now so the discipline is in place when a second async consumer appears (e.g., notifications, CSV exports).

## Decision

Use the **transactional outbox pattern** when a state change must notify others: the service writes — **in one database transaction** — the domain row plus an `event_outbox` row (and, for security-relevant actions, an `audit_log` row). Because all are in the same tx, they commit or roll back together: **no dual write.**

A separate **outbox-relay worker** polls `event_outbox WHERE status='pending'` and publishes to the bus (Redis pub/sub or a managed SNS/SQS), marking rows `published`. Consumers are **idempotent** (dedupe on event id) because at-least-once delivery means a relay crash between publish and mark can re-deliver.

## Alternatives considered

- **Direct dual write** (DB + bus in the handler) — rejected: the inconsistency window is the whole problem; no amount of retry logic closes it cleanly.
- **Change Data Capture (Debezium/logical replication)** — viable and avoids the polling relay, but adds infrastructure (a CDC pipeline) and couples event shape to table shape. Deferred; the outbox is simpler and the relay is swappable for CDC later without changing producers.
- **Two-phase commit across DB and bus** — rejected: XA-style 2PC is operationally heavy, poorly supported by managed buses, and a latency/availability drag.

## Consequences

**Easier:**
- **Atomicity:** an event exists if and only if its change committed. Audit is guaranteed alongside the action.
- The **actual event bus is swappable** — producers only write a table row; only the relay knows the broker.

**Harder / must uphold:**
- Consumers **must be idempotent** — at-least-once delivery is a given, exactly-once is not.
- The relay adds polling latency (sub-second to seconds) between commit and publish; fine for notifications/exports, not for synchronous needs.
- `event_outbox` needs an efficient `status='pending'` index and a retention/cleanup story so it doesn't grow unbounded.

## MVP status

At MVP, no `event_outbox` table is created (see [DATABASE_SCHEMA.md §1](../DATABASE_SCHEMA.md#1-scope) — `event_outbox` is not listed). The first async consumer that needs cross-module notification will introduce it. AI jobs are dispatched directly to BullMQ inside the same request handler and use `ai_job.idempotency_key` for dedupe, so they don't need outbox semantics.