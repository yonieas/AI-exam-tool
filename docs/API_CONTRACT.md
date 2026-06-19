# API Contract — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [PRD.md](./PRD.md) · [ARCHITECTURE.md §7](./ARCHITECTURE.md) · [AUTH.md](./AUTH.md) · [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)
> **Consumed by:** frontend (FE↔BE handshake), integration tests, generated OpenAPI.

This is the **wire contract** for the FastAPI monolith. Every MVP endpoint, auth requirement, request shape, response shape, and status codes. Fields map to columns in [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md). All endpoints require an authenticated teacher (owner-scoped) unless marked **public**.

---

## 1. Conventions

| Concern | Rule |
|---|---|
| **Base URL** | `https://app.example.com/api` |
| **Versioning** | URI-versioned: all paths under `/api/v1` |
| **Format** | JSON only, UTF-8. Timestamps ISO-8601 UTC |
| **IDs** | UUID v7 strings |
| **Money** | Not used at MVP — `max_score` is `numeric` not money |
| **Auth** | `Authorization: Bearer <access_jwt>`. Refresh via HttpOnly cookie |
| **Naming** | `snake_case` on the wire |
| **Pagination** | Cursor-based (§1.2) |
| **Idempotency** | `Idempotency-Key` required on AI-job creation & finalize (§1.4) |
| **Errors** | RFC 7807 `application/problem+json` (§1.3) |
| **Uploads** | Two-step: `POST /uploads/presign` → MinIO PUT → `storage_key` (§1.5) |

### 1.1 Standard headers

**Request**
```
Authorization: Bearer <access_jwt>
Content-Type: application/json
Idempotency-Key: <uuid>          # writes that must not double-apply
X-Request-Id: <uuid>             # optional client trace id
```

**Response**
```
X-Request-Id: <uuid>
```

### 1.2 Pagination

```
GET /api/v1/students?limit=50&cursor=<opaque>
```
```jsonc
{
  "data": [ /* items */ ],
  "page": { "next_cursor": "eyJpZCI6Li4ufQ", "limit": 50, "has_more": true }
}
```
- `limit` default 50, max 200.

### 1.3 Error model (RFC 7807)

```jsonc
{
  "type":   "https://errors.example.com/forbidden",
  "title":  "Forbidden",
  "status": 403,
  "code":   "FORBIDDEN",
  "detail": "Resource belongs to another owner.",
  "instance": "/api/v1/exams/0192...",
  "request_id": "0192f3a1-...",
  "errors": [ { "field": "due_at", "message": "..." } ]   // on 422 only
}
```

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `BAD_REQUEST` | Malformed request |
| 401 | `UNAUTHENTICATED` | Missing/invalid/expired token |
| 403 | `FORBIDDEN` | Owner mismatch |
| 404 | `NOT_FOUND` | Resource not found in this owner's scope |
| 409 | `CONFLICT` | Unique violation / illegal state transition |
| 422 | `VALIDATION` | Body validation failed (`errors[]` populated) |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL` | Unexpected |

### 1.4 Idempotency

`POST /api/v1/exams/:id/generate`, `POST /api/v1/grading-runs/:id/items` (file upload), `POST /api/v1/grading-runs/:id/finalize` require `Idempotency-Key: <uuid>`. The server stores `(owner_id, key) → response` in `ai_job.idempotency_key`. Replaying the same key returns the original result.

### 1.5 Uploads (MinIO)

```http
POST /api/v1/uploads/presign
{ "kind": "source_image", "exam_id": "...", "filename": "page.jpg", "mime_type": "image/jpeg" }

201 →
{ "upload_url": "https://minio.example.com/sx-uploads/...?X-Amz-...",
  "storage_key": "sources/0192.../0192.../page.jpg",
  "method": "PUT",
  "headers": { "Content-Type": "image/jpeg" } }
```
The client PUTs the file directly to MinIO. Subsequent endpoints reference the blob via `storage_key` or `file_asset_id`.

### 1.6 Async AI jobs

Heavy AI work returns `202 Accepted` + an `ai_job` resource. The client polls `/ai-jobs/:id`.

```jsonc
// 202
{ "ai_job": { "id": "0192...", "job_type": "grading", "job_status": "queued",
              "poll_url": "/api/v1/ai-jobs/0192..." } }
```
Lifecycle: `queued → processing → done | failed`. See [DATABASE_SCHEMA.md §11](./DATABASE_SCHEMA.md).

---

## 2. Public (unauthenticated) endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/auth/google` | Redirect to Google OAuth |
| `GET` | `/auth/google/callback` | OAuth callback |
| `POST` | `/auth/refresh` | Rotate refresh → new access (cookie) |
| `POST` | `/auth/logout` | Revoke session |
| `GET` | `/livez` / `/readyz` | Health probes |

### 2.1 `GET /auth/google`
Redirects to Google with `state` and PKCE.

### 2.2 `GET /auth/google/callback?code=…&state=…`
On success → `Set-Cookie: refresh=…; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` + JSON `{ access_token, expires_in: 900, user: { id, email, full_name } }`. 302 redirect to `/dashboard`.

---

## 3. Authenticated endpoints

All require `Authorization: Bearer <access_jwt>`. All queries are owner-scoped.

### 3.0 Me

| Method | Path | Description |
|---|---|---|
| `GET` | `/me` | Current user (id, email, full_name, avatar_url) |

### 3.1 Subjects

| Method | Path | Notes |
|---|---|---|
| `GET` | `/subjects` | List, cursor-paginated |
| `POST` | `/subjects` | Create |
| `GET` | `/subjects/:id` | Detail |
| `PATCH` | `/subjects/:id` | Rename / change code |
| `DELETE` | `/subjects/:id` | Soft-delete (fails if used by an exam) |

```jsonc
// POST /subjects
{ "name": "Physics", "code": "PHYS" }
// 201 → { "id": "...", "name": "Physics", "code": "PHYS", "created_at": "..." }
```

### 3.2 Classes

| Method | Path | Notes |
|---|---|---|
| `GET` | `/classes` | List |
| `POST` | `/classes` | Create |
| `GET` | `/classes/:id` | Detail (with subjects[] and student_count) |
| `PATCH` | `/classes/:id` | Rename / change grade_level |
| `DELETE` | `/classes/:id` | Soft-delete |
| `GET` | `/classes/:id/subjects` | List subject ids taught |
| `PUT` | `/classes/:id/subjects` | Replace subject set `{ "subject_ids": [...] }` |
| `GET` | `/classes/:id/students` | List enrolled students |
| `POST` | `/classes/:id/enrollments` | Enroll one student `{ "student_id": "..." }` |
| `DELETE` | `/classes/:id/enrollments/:student_id` | Unenroll |

```jsonc
// POST /classes
{ "name": "Grade 10-A", "grade_level": 10 }
// 201 → { "id": "...", "name": "Grade 10-A", "grade_level": 10, "subject_ids": [], "student_count": 0 }
```

### 3.3 Students

| Method | Path | Notes |
|---|---|---|
| `GET` | `/students` | List, filter by `class_id` |
| `POST` | `/students` | Create single student |
| `GET` | `/students/:id` | Detail |
| `PATCH` | `/students/:id` | Edit name / student_code / email / extra_columns |
| `DELETE` | `/students/:id` | Soft-delete |

#### 3.3.1 Excel import

| Method | Path | Notes |
|---|---|---|
| `POST` | `/students/import/preview` | Multipart: `file=@students.xlsx`. Returns detected headers + first 5 rows. |
| `POST` | `/students/import` | Multipart: `file` + JSON field mapping |

**Preview response**
```jsonc
{
  "columns": [
    { "letter": "A", "header": "Student Name",  "sample_values": ["Aarav","Bea","Cira"] },
    { "letter": "B", "header": "Student ID",    "sample_values": ["S001","S002","S003"] },
    { "letter": "C", "header": "Email",         "sample_values": ["a@x","b@x","c@x"] },
    { "letter": "D", "header": "Homeroom",      "sample_values": ["10A","10A","10B"] }
  ],
  "row_count": 30
}
```

**Import body**
```jsonc
{
  "mapping": {
    "name":         "A",          // canonical field → column letter
    "student_code": "B",
    "email":        "C",
    "extra_columns": {
      "homeroom": "D"
    }
  },
  "rows": "process_all"           // or "process_indices": [0,1,2]
}
```
- `name` mapping is required.
- Extra columns are stored in `student.extra_columns`.
- `Idempotency-Key` required (avoid double-import on retry).

```jsonc
// 200
{ "imported": 30, "skipped": 0, "errors": [ { "row": 5, "message": "..." } ] }
```

### 3.4 Exams

| Method | Path | Notes |
|---|---|---|
| `GET` | `/exams` | List, filter by `subject_id`, `status`, `q` |
| `POST` | `/exams` | Create draft |
| `GET` | `/exams/:id` | Detail |
| `PATCH` | `/exams/:id` | Edit title / units / counts (only when `status=draft`) |
| `DELETE` | `/exams/:id` | Soft-delete |
| `POST` | `/exams/:id/generate` | Trigger AI generation (202 + ai_job) |
| `POST` | `/exams/:id/publish` | Mark published (after all questions approved) |
| `POST` | `/exams/:id/close` | Close |

#### 3.4.1 Create + generate

```jsonc
// POST /exams
{
  "subject_id": "0192...",
  "title": "Physics Unit 1",
  "units": ["Kinematics", "Forces"],
  "question_type_mode": "both",
  "total_count": 10,
  "mcq_count": 7,
  "essay_count": 3,
  "generation_config": { "language": "en", "difficulty": "medium" },
  "source": { "kind": "image", "file_asset_id": "0192..." }   // or "pdf", or omit
}
// 201 → exam with status="draft"
```

```jsonc
// POST /exams/:id/generate   (Idempotency-Key required)
// Request: empty (uses the exam's config + source)
// 202
{ "ai_job": { "id": "...", "job_type": "question_generation", "job_status": "queued",
              "poll_url": "/api/v1/ai-jobs/..." } }
// On done: exam.status → "in_review", questions created with status="in_review"
```

### 3.5 Questions

| Method | Path | Notes |
|---|---|---|
| `GET` | `/exams/:id/questions` | List ordered by position |
| `POST` | `/exams/:id/questions` | Manual add `{ type, prompt, max_score, options?, rubric? }` |
| `GET` | `/exams/:id/questions/:qid` | Detail |
| `PATCH` | `/exams/:id/questions/:qid` | Edit (any field; AI metadata preserved) |
| `POST` | `/exams/:id/questions/:qid/approve` | Approve (status→approved) |
| `POST` | `/exams/:id/questions/:qid/reject` | Reject (status→draft; teacher must rewrite) |

```jsonc
// A question (MCQ)
{
  "id": "0192...", "position": 1, "type": "mcq", "status": "approved",
  "prompt": "An object at rest stays at rest unless…",
  "options": { "choices": [
    { "label": "acted on by a net force", "is_correct": true },
    { "label": "moving at constant velocity", "is_correct": false }
  ] },
  "max_score": 1.0,
  "ai_meta": { "model": "MiniMax-M2.7", "source_citation": "p. 42 §3.1", "confidence": 0.92 }
}
```

### 3.6 Exam files & PDFs

| Method | Path | Notes |
|---|---|---|
| `GET` | `/exams/:id/files` | List file assets (questions_pdf, answers_pdf, source_*, …) |
| `POST` | `/exams/:id/files` | Register a file already uploaded via `/uploads/presign` `{ kind, storage_key, original_name, mime_type, size_bytes }` |
| `PATCH` | `/exams/:id/files/:fid` | Rename `{ "original_name": "physics_unit1_q.pdf" }` |
| `DELETE` | `/exams/:id/files/:fid` | Soft-delete |
| `GET` | `/exams/:id/files/:fid/download` | 302 to MinIO presigned GET URL (5 min TTL) |
| `POST` | `/exams/:id/files/:fid/regenerate` | Re-render questions_pdf / answers_pdf |

#### 3.6.1 Question / answer PDF endpoints (convenience)

| Method | Path | Returns |
|---|---|---|
| `GET` | `/exams/:id/pdf/questions` | 302 → MinIO URL of `questions.pdf` (regenerates if missing) |
| `GET` | `/exams/:id/pdf/answers` | 302 → MinIO URL of `answers.pdf` |

### 3.7 Grading runs

| Method | Path | Notes |
|---|---|---|
| `GET` | `/grading-runs` | List |
| `POST` | `/grading-runs` | Create |
| `GET` | `/grading-runs/:id` | Detail + items[] summary |
| `DELETE` | `/grading-runs/:id` | Soft-delete (only if `status != finalized`) |
| `POST` | `/grading-runs/:id/items` | Register student answer file `{ student_id, file_asset_id }` — enqueues AI grading |
| `GET` | `/grading-runs/:id/items/:itemId` | Detail with responses[] |
| `PATCH` | `/grading-runs/:id/items/:itemId/responses/:rid` | Teacher override `{ teacher_score, teacher_rationale? }` |
| `POST` | `/grading-runs/:id/items/:itemId/waive-flag` | Approve flagged item without override |
| `POST` | `/grading-runs/:id/finalize` | Finalize (requires no flagged-unreviewed items) — Idempotency-Key required |
| `GET` | `/grading-runs/:id/results.csv` | CSV export of per-student totals |

#### 3.7.1 Create grading run

```jsonc
// POST /grading-runs
{
  "exam_id": "0192...",
  "title": "Physics Unit 1 – Period 3",
  "benchmark_kind": "exam_answer_key"   // or "uploaded" + file_asset_id
}
// 201 → { id, status:"draft", max_score_total, ... }
```

#### 3.7.2 Register student answer + AI grade

```jsonc
// POST /grading-runs/:id/items   (Idempotency-Key required)
{
  "student_id": "0192...",
  "file_asset_id": "0192..."          // uploaded via /uploads/presign
}
// 202
{ "ai_job": { "id": "...", "job_type": "grading", "job_status": "queued",
              "poll_url": "/api/v1/ai-jobs/..." } }
// On done: grading_item.status="ai_done"; responses[] populated; flagged if any question flagged
```

#### 3.7.3 Override

```jsonc
// PATCH /grading-runs/:id/items/:itemId/responses/:rid
{ "teacher_score": 0.8, "teacher_rationale": "Partial credit for showing work" }
// 200 → updated response; overridden=true; grading_item.flagged recomputed
```

#### 3.7.4 Finalize gate

```jsonc
// POST /grading-runs/:id/finalize   (Idempotency-Key required)
// 409 CONFLICT if any item is flagged && !reviewed
// 200
{ "id": "...", "status": "finalized", "finalized_at": "2026-06-18T...",
  "summary": { "n_items": 15, "mean": 0.78, "median": 0.82 } }
```

### 3.8 AI jobs

| Method | Path | Notes |
|---|---|---|
| `GET` | `/ai-jobs/:id` | Poll status |

```jsonc
// 200
{ "id": "...", "job_type": "grading", "job_status": "done",
  "queued_at": "...", "started_at": "...", "completed_at": "...",
  "total_tokens_input": 1230, "total_tokens_output": 312, "cost_usd_micro": 12345,
  "ai_provider": "minimax", "model": "MiniMax-M2.7" }
```

### 3.9 Uploads (presigned)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/uploads/presign` | `{ kind, exam_id?, grading_run_id?, filename, mime_type, size_bytes }` → `{ upload_url, storage_key, method, headers }` |

---

## 4. Endpoint → FR coverage

| FR | Endpoint(s) |
|---|---|
| FR-AUTH.1 | `/auth/google`, `/auth/google/callback` |
| FR-AUTH.2 | `/auth/refresh` |
| FR-AUTH.3 | `/auth/logout` |
| FR-SC.1 | `/subjects` |
| FR-SC.2 | `/classes` |
| FR-SC.3 | `/classes/:id/subjects` |
| FR-SC.4 | `/classes/:id/enrollments`, `/classes/:id/students` |
| FR-S.1 | `POST /students` |
| FR-S.2 | `/students/import/preview`, `/students/import` |
| FR-S.3 | `GET/PATCH/DELETE /students/:id` |
| FR-S.4 | `/classes/:id/enrollments` |
| FR-E.1 | `POST /exams` |
| FR-E.2 | `POST /exams/:id/files` (source kind) |
| FR-E.3 | `POST /exams/:id/generate` |
| FR-E.4 | `/exams/:id/questions`, `/approve`, `/reject` |
| FR-E.5 | `POST /exams/:id/questions` |
| FR-F.1 | `POST /exams/:id/files` + regenerate |
| FR-F.2 | `PATCH /exams/:id/files/:fid` |
| FR-F.3 | `GET /exams/:id/pdf/questions`, `/answers` |
| FR-F.4 | `GET /exams/:id/files/:fid/download` |
| FR-G.1 | `POST /grading-runs` |
| FR-G.2 | `POST /grading-runs/:id/items` |
| FR-G.3 | `GET /grading-runs/:id/items/:itemId` |
| FR-G.4 | `/items/:itemId/waive-flag`, finalize gate |
| FR-G.5 | `PATCH /items/:itemId/responses/:rid` |
| FR-G.6 | `POST /grading-runs/:id/finalize`, `/results.csv` |
| FR-G.7 | manual entry via `PATCH /responses/:rid` without AI |
| FR-AI.1 | `/ai-jobs/:id` |
| FR-AI.2 | `Idempotency-Key` on generate/items/finalize |
| FR-AI.3 | `ai_job.ai_provider` exposes active adapter |
| FR-AI.4 | enforced inside `ai/structured.py` (see AI_SUBSYSTEM_SPEC) |

---

## 5. Conventions for the frontend

- **Auth bootstrap:** call `GET /me` on app load.
- **Optimistic vs async:** CRUD writes are sync (return updated resource). **AI generate/grade are async** — show a job-status spinner, poll `/ai-jobs/:id`.
- **Errors:** branch on `code` (e.g. `VALIDATION` → show `errors[]`; `CONFLICT` → toast).
- **Uploads:** always two-step via `/uploads/presign`. Never POST binary to JSON endpoints.
- **Lists:** cursor-paginated; load more via `next_cursor`.

---

## 6. Open items

- **Bulk student answer upload (zip of PDFs named by student_id):** deferred to P2; per-student upload is MVP.
- **Bulk approve questions:** could be a `POST /exams/:id/questions/approve-all` — confirm need. Default to per-question approve.
- **OpenAPI generation:** generate from FastAPI route decorators (`openapi.yaml`); this doc is the human-readable companion.