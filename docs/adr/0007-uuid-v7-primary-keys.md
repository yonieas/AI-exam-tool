# ADR-007 — UUID v7 primary keys

> **Status:** Accepted
> **Date:** 2026-06-18
> **Deciders:** Architecture team
> **Related:** [DATABASE_SCHEMA.md §4.1](../DATABASE_SCHEMA.md#41-uuid-v7-generator) · [ERD.md §1](../ERD.md#1-modeling-conventions)

## Context

Every entity needs a primary key. The candidates and their problems:

- **Auto-increment `bigint`** — compact and index-friendly, but **enumerable** (a sequential ID in a URL leaks row counts and invites IDOR probing) and awkward to assign before insert (clients/distributed components can't mint IDs offline).
- **UUID v4 (random)** — non-enumerable and client-mintable, but **random**, so it scatters B-tree inserts across the index, causing page splits and poor locality at scale (the `ai_job` and `grading_item` tables are the most write-heavy at exam-grading bursts).
- **UUID v7 (time-ordered)** — non-enumerable, client-mintable, **and** time-prefixed so inserts are largely sequential, preserving index locality.

## Decision

**Use UUID v7 as the primary key type everywhere** ([DATABASE_SCHEMA.md §4.1](../DATABASE_SCHEMA.md#41-uuid-v7-generator)).

We pin **PostgreSQL 16** ([ARCHITECTURE.md §4](../ARCHITECTURE.md)), which has no native `uuidv7()` (that arrives in PG18). So we ship a **`uuid_generate_v7()` SQL fallback** so DB-side `DEFAULT`s work for rows inserted by migrations/seeds/admin tools. **App-side generation** (a Python UUID v7 library, e.g. `uuid6` or `uuid_utils`) is equally valid and recommended as the source of truth for portability; the DB default is the safety net.

## Alternatives considered

- **`bigserial`** — rejected: enumerable PKs in URLs are an information-leak/IDOR risk.
- **UUID v4** — rejected: random insert order degrades write throughput and index locality on the largest tables; v7 keeps the non-enumerability while restoring locality.
- **ULID / KSUID** — equivalent time-ordered properties, but UUID v7 is a standard Postgres `uuid` type with native support coming in PG18; no custom column type needed.

## Consequences

**Easier:**
- Non-enumerable IDs (no count leakage, harder IDOR), client-mintable (offline/distributed inserts), and time-ordered for index locality on append-heavy tables.
- Clean upgrade path: on **PG18+**, swap `uuid_generate_v7()` → native `uuidv7()` and drop the fallback.

**Harder / must uphold:**
- **Decide the source of truth** — app-side vs DB default — before the first migration, and apply it consistently. Recommended: app-side, DB default as fallback.
- UUIDs are 16 bytes vs 8 for `bigint` — marginally larger indexes/FKs; accepted for the security + distribution benefits.
- The PG16 fallback function is custom SQL to maintain until the PG18 upgrade.
