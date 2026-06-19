# ADR-005 — Confidence + flag-for-review gate on AI grades

> **Status:** Accepted
> **Date:** 2026-06-18
> **Deciders:** Architecture team
> **Related:** [AI_SUBSYSTEM_SPEC.md §5.5, §5.6](../AI_SUBSYSTEM_SPEC.md) · [ARCHITECTURE.md §7.3](../ARCHITECTURE.md) · [ADR-004](./0004-structured-output-only-ai.md)

## Context

AI grades affect a student's record. An incorrect AI grade that auto-publishes is both an educational harm and a fairness problem. The product's value proposition ([PRD.md](../PRD.md)) is that AI **saves teachers time** — so the gate must help, not negate the benefit.

The scope is **one teacher** (no per-school policy variants). We need a single, clear rule: what auto-publishes, what doesn't, and how the teacher is informed.

## Decision

**AI is assistive, never unauditable; low-confidence items require explicit teacher review before finalize.**

- **Generation** ([AI_SUBSYSTEM_SPEC.md §4](../AI_SUBSYSTEM_SPEC.md)): AI-generated questions land `status='in_review'` — **nothing is student-facing until a teacher approves**. The teacher reviews/edits/approves each question and only then publishes the exam.
- **Grading confidence routing** ([AI_SUBSYSTEM_SPEC.md §5.5](../AI_SUBSYSTEM_SPEC.md)):
  - Each graded response carries `confidence ∈ [0,1]` and a `flagged` boolean.
  - `flagged = true` when `confidence < 0.7` OR the rationale mentions OCR / handwriting / ambiguity.
  - `grading_item.flagged = OR(per-question flags)`.
- **Finalize gate** ([AI_SUBSYSTEM_SPEC.md §5.6](../AI_SUBSYSTEM_SPEC.md)): `POST /grading-runs/:id/finalize` returns `409 CONFLICT { code: "FLAGGED_ITEMS_REMAIN" }` while any item is `flagged && !reviewed`. The teacher either **overrides** the score (`PATCH /items/:itemId/responses/:rid`) or **waives the flag** (`POST /items/:itemId/waive-flag`) for each flagged item.
- **Teacher override** ([AI_SUBSYSTEM_SPEC.md §5.6](../AI_SUBSYSTEM_SPEC.md)): any AI score is editable; overrides persist as `teacher_score`, with `overridden=true` recorded for audit and calibration.
- **Default threshold:** 0.7, configurable per exam (P2). Default lives in `user.settings.default_confidence_threshold`.

## Alternatives considered

- **Full auto-grading, teacher spot-checks after publish** — rejected: a wrong grade is already in front of students before correction; "correction-after-harm" is exactly the trust failure we're avoiding.
- **100% human review of every item** — rejected: negates the time-saving value; high-confidence MCQ doesn't need a human, and forcing it trains rubber-stamping.
- **Per-school configurable thresholds** — deferred to P2: single-teacher MVP has one threshold (in `user.settings`).

## Consequences

**Easier:**
- Trust and fairness: a human is accountable for every consequential grade.
- Teacher overrides become training signal for the eval harness ([AI_SUBSYSTEM_SPEC.md §8](../AI_SUBSYSTEM_SPEC.md)).

**Harder / must uphold:**
- The finalize gate is critical: it needs an explicit test + a production guard metric (count of finalizes with `flagged && !reviewed` items must be 0). Lint rule + integration test enforce it.
- The review queue UX ([COMPONENT_SPEC.md §7 `<GradingItemsTable>`, §8 `<ResponsesTable>`](../COMPONENT_SPEC.md)) must be efficient enough that the gate saves time net of review.
- Confidence thresholds need tuning from real override data — calibration is ongoing.