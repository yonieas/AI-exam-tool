# Code & Security Review Findings

## Backend (API) — Critical Issues

### 1. Owner-scoping violations in ClassRepo (SEV1)
**Files:** `api/app/modules/classes/repo.py`
**Methods:** `get_class_subject_ids` (line 84), `clear_class_subjects` (line 90), `count_enrolled` (line 101), `get_enrolled_students` (line 108)

These methods query `ClassSubject`, `ClassEnrollment`, and `Student` tables **without filtering by `owner_id`**. An attacker authenticated as owner A could enumerate subjects, students, and enrollments belonging to owner B by supplying a `class_id` owned by B.

**Impact:** Cross-owner data leak — SEV1 per CLAUDE.md invariants.
**Fix:** Add `ClassSubject.owner_id == owner_id` / `ClassEnrollment.owner_id == owner_id` to all queries. The composite FK `(class_id, owner_id)` on `ClassSubject` prevents **writing** cross-owner rows but does **not** prevent **reading** them because that constraint is never enforced on SELECT.

### 2. Race condition in `add_class_subjects` / `clear_class_subjects`
**File:** `api/app/modules/classes/repo.py:90-95`
`clear_class_subjects` deletes and `add_class_subjects` inserts in separate operations with no locking. Under concurrent requests, subject assignments can be lost or duplicated.
**Fix:** Wrap in a single transaction with `SELECT ... FOR UPDATE` on the parent class row, or use a single `REFRESH`-style operation.

### 3. Missing owner_id in `GradingItemResponse` model
**File:** `api/app/models/grading.py:77-94`
`GradingItemResponse` has **no `owner_id` column** and **no composite FK** through `grading_item`. This means:
- Owner-scoped queries cannot filter on this table directly.
- There is no referential integrity guard against a response being linked to a grading_item from another owner.

**Fix:** Add `owner_id` column and `ForeignKeyConstraint(["grading_item_id", "owner_id"], ["grading_item.id", "grading_item.owner_id"])`.

### 4. Missing owner_id in `QuestionOption` model
**File:** `api/app/models/exam.py:90-98`
Same issue — no `owner_id`, no composite FK. The FK to `question.id` alone does not prevent cross-owner access.
**Fix:** Add `owner_id` and composite FK.

## Backend — Medium Issues

### 5. PII in AI adapter logs
**File:** `api/app/ai/minimax_adapter.py:89`
Logs up to 200 characters of raw AI output on JSON parse failure. If the AI returns student answers or PII in the error path, it leaks into logs.
**Fix:** Log only token counts and error type, not raw content. Or hash the content.

### 6. CORS too permissive for production
**File:** `api/app/main.py:98-105`
Hardcoded to `localhost:3000/3050`. For production, CORS origins must be configurable via env var.
**Fix:** Read `CORS_ORIGINS` from settings instead of hardcoding.

### 7. ENUM creation not idempotent
**File:** `api/app/main.py:72-78`
Uses `CREATE TYPE` without `IF NOT EXISTS`. While PostgreSQL DDL is transactional, concurrent startup could race.
**Fix:** Use `CREATE TYPE IF NOT EXISTS` (Postgres 9.3+) or check existence first.

### 8. `datetime.utcnow()` will be deprecated
**File:** Multiple model files use `default=datetime.utcnow`.
In Python 3.12+, `datetime.utcnow()` emits deprecation warnings. Use `datetime.now(timezone.utc)` or `func.now()`.
**Fix:** Create a helper `def utcnow() -> datetime: return datetime.now(timezone.utc)` and use everywhere.

## Backend — Low / Suggestions

### 9. Redundant UUID generation
**File:** `api/app/models/user.py:30-48` generates UUIDv7 app-side, while `api/app/db.py` line 52 also tries to create `uuid_generate_v7()` PG extension. Two sources of truth — pick one. Prefer DB default for resilience and app-side as fallback.

### 10. Missing composite FKs on `AIJob` cross-references
`AIJob.exam_id` has a composite FK `(exam_id, owner_id)`, but `GradingItemResponse.question_id` has a simple FK `→ question.id` without owner_id — referential integrity is weaker.

### 11. Worker startup in same process
**File:** `api/app/main.py:43-44` conditionally starts the BullMQ worker in the API process. In production, the worker runs as a separate process per BUILD_SEQUENCE.md. The `EXAMTOOL_WORKER_DISABLED` env var controls this — document this properly in deployment config.

## Frontend — Critical Issues

### 12. JWT stored in localStorage (XSS-susceptible)
If the frontend stores JWTs in `localStorage`, any XSS vulnerability can exfiltrate tokens. Use `httpOnly` cookies with CSRF tokens instead where possible.
**Verification needed:** Check `web/app/providers.tsx` and the auth module for token storage mechanism.

### 13. User-provided data rendered without sanitization
**File:** `web/app/(app)/dashboard/dashboard-client.tsx` and `page.tsx`
Exam titles, student names, and subject names come from the API and are rendered via React. React escapes by default, but if `dangerouslySetInnerHTML` is used anywhere, it's an XSS vector.
**Recommendation:** Audit for `dangerouslySetInnerHTML` usage. Use DOMPurify if user HTML is required.

## Frontend — Medium Issues

### 14. TanStack Query cache may span owners
If the query key does not include `owner_id`, cached data for one user could be shown to another during SSR or if not invalidated on auth change.
**Fix:** Include `owner_id` in every query key.

### 15. Missing error boundaries
API failures may cause unhandled promise rejections or blank screens. Add React error boundaries around major sections.

## Frontend — Low / Suggestions

### 16. Missing TypeScript strictness
Some API response types use `any`. Define proper response interfaces for all API calls.

### 17. Unused dependencies
`web/package.json` may include packages not used at runtime. Audit with `depcheck`.

## Security Review Summary

| OWASP Category | Status |
|---|---|
| A01: Injection | No SQL injection found; owner-scoping gaps allow data enumeration |
| A02: Broken Auth | JWT verification is correct; service-layer owner checks missing |
| A03: Sensitive Data Exposure | AI logs may contain PII; review log retention policy |
| A04: XXE | N/A |
| A05: Broken Access Control | **SEV1**: ClassRepo queries lack `owner_id` filters |
| A06: Security Misconfiguration | CORS hardcoded; ENUM creation not idempotent |
| A07: XSS | Potential if `dangerouslySetInnerHTML` is used |
| A08: Insecure Deserialization | N/A |
| A09: Known Vulnerabilities | Run `npm audit` and `pip-audit` in CI |
| A10: Insufficient Logging | Logs exist but may contain PII — add log redaction |

**Key recommendations before merge:**
1. Add `owner_id` to all ClassRepo queries that touch ClassSubject, ClassEnrollment, Student
2. Add `owner_id` to GradingItemResponse and QuestionOption models
3. Make CORS origins configurable via env var
4. Add CI pipeline to run `pip-audit` and `npm audit`
5. Add owner-isolation integration tests per BACKEND_CONVENTIONS §3
