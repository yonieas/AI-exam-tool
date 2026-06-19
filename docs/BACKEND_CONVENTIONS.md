# Backend Conventions — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [ARCHITECTURE.md](./ARCHITECTURE.md) · [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) · [API_CONTRACT.md](./API_CONTRACT.md) · [AUTH.md](./AUTH.md) · [AI_SUBSYSTEM_SPEC.md](./AI_SUBSYSTEM_SPEC.md)
> **Consumed by:** [BUILD_SEQUENCE.md](./BUILD_SEQUENCE.md)

How the **FastAPI monolith** and the **AI worker** are built: module layout mapped to ERD subdomains, the request → service → repo flow with owner scoping, DTO/validation, error mapping, async AI jobs, file handling (MinIO + presigned URLs), Excel parsing, PDF generation, and testing.

> **Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2 + BullMQ (Redis) + openpyxl + WeasyPrint + minio-py. Re-confirm version-specific APIs at build time per the Context7 rule.

---

## 1. Module layout

One module per ERD subdomain. Modules own their tables; cross-module interaction is via injected services only.

```
api/
  main.py                       # FastAPI app, mounts routers + middleware
  config.py                     # 12-factor settings (env)
  deps.py                       # FastAPI Depends helpers
  db.py                         # SQLAlchemy engine + SessionLocal
  errors.py                     # exception types + RFC 7807 filter
  models/                       # SQLAlchemy ORM
    user.py
    subject.py
    class_.py
    student.py
    exam.py
    question.py
    grading.py
    file_asset.py
    ai_job.py
  schemas/                      # Pydantic DTOs (request/response)
  modules/
    auth/                       # Google OAuth, JWT sessions, Redis
    subjects/
    classes/
    students/
    exams/
    questions/
    grading/
    files/                      # MinIO presigned URLs, PDF generation
    uploads/                    # /uploads/presign
    ai_jobs/                    # /ai-jobs/:id polling
  ai/                           # AI module (in-process)
    provider.py                 # AIProvider Protocol
    minimax_adapter.py       # default implementation (openai SDK → MiniMax API)
    structured.py               # schema validation + score clamping
    prompts/
    tasks/
      generation.py
      grading.py
    eval/
  workers/
    ai_worker.py                # BullMQ consumer (separate process)
  storage/
    minio_client.py
    pdf_renderer.py
    excel_parser.py
  migrations/                   # Alembic
tests/
  unit/
  integration/                  # Testcontainers (Postgres + MinIO + Redis)
  owner_isolation/              # cross-owner access returns zero rows
  ai_eval/                      # golden-set evals
```

---

## 2. Layered flow

```
Route (FastAPI) → validates DTO, no business logic, returns DTO
   ↓
Service   → business logic, owner scoping, orchestrates AI / storage / DB
   ↓
Repository → only layer touching SQL; every method takes `owner_id` first
   ↓
Database   → Postgres + composite tenant FKs (defense-in-depth)
```

- **Routes** are thin: declare auth dependency, bind Pydantic schemas, delegate to a service.
- **Services** own transactions (one `AsyncSession` per request via dependency) and orchestrate AI / storage / events.
- **Repositories** are the only layer that imports SQLAlchemy ORM models and emits SQL.

---

## 3. Owner scoping (auth/integrity)

Every request runs through `get_current_user()` (decodes JWT → `User`). Every repository method **requires** `owner_id: UUID` as the first argument and **adds** `WHERE owner_id = :owner_id` to every query.

```python
# modules/exams/repo.py
class ExamRepo:
    async def list(self, owner_id: UUID, *, subject_id: UUID | None = None,
                   status: ExamStatus | None = None, cursor: str | None = None,
                   limit: int = 50) -> list[Exam]:
        stmt = select(Exam).where(Exam.owner_id == owner_id, Exam.deleted_at.is_(None))
        if subject_id: stmt = stmt.where(Exam.subject_id == subject_id)
        if status:     stmt = stmt.where(Exam.status == status)
        # cursor + limit
        return (await self.session.scalars(stmt)).all()

    async def get(self, owner_id: UUID, exam_id: UUID) -> Exam | None:
        return await self.session.get(Exam, exam_id, options=[...])
        # ↑ followed by an explicit owner_id check inside the service
```

**Defense-in-depth:**
1. Application: every repo query filters `owner_id`.
2. Database: composite `(parent_id, owner_id) → parent(id, owner_id)` FKs on children (see [DATABASE_SCHEMA.md §4.3](./DATABASE_SCHEMA.md)).
3. CI: the `owner_isolation` test suite sets `owner_id=A`, attempts to read/write B's rows, asserts empty/conflict.

**Service-level ownership check:**
```python
async def get(self, owner_id: UUID, exam_id: UUID) -> Exam:
    exam = await self.repo.get(owner_id, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found.")
    if exam.owner_id != owner_id:        # belt-and-braces; shouldn't be reachable
        raise ForbiddenError("Resource belongs to another owner.")
    return exam
```

A cross-owner resource → `404 NOT_FOUND` (we never confirm existence across owners).

---

## 4. Schemas & validation

- **Request schemas** are Pydantic v2 models; FastAPI validates body / query / path. Validation failures → `422 VALIDATION` with `errors[]` (see [API_CONTRACT.md §1.3](./API_CONTRACT.md)).
- **Field names** match the API contract: `snake_case` on the wire.
- **IDs** are `UUID4` strings on input; serialized as `UUID v7` strings on output.
- **Internal ORM fields** are mapped to DTOs explicitly — never return an ORM instance from a route. This prevents leaking columns not in the contract.

---

## 5. Errors

A single **exception filter** maps everything to RFC 7807:

| Exception | HTTP | `code` |
|---|---|---|
| `ValidationError` (Pydantic) | 422 | `VALIDATION` |
| `UnauthenticatedError` | 401 | `UNAUTHENTICATED` |
| `ForbiddenError` | 403 | `FORBIDDEN` |
| `NotFoundError` | 404 | `NOT_FOUND` |
| `ConflictError` | 409 | `CONFLICT` (includes `FLAGGED_ITEMS_REMAIN`) |
| `QuotaExceededError` | 429 | `QUOTA_EXCEEDED` |
| `RateLimitedError` | 429 | `RATE_LIMITED` |
| (anything else) | 500 | `INTERNAL` |

All responses carry `X-Request-Id` matching the trace id (see [OBSERVABILITY.md](./OBSERVABILITY.md)).

---

## 6. Async AI jobs (BullMQ)

Heavy work (generation, grading) goes through BullMQ. The route returns `202 + ai_job`; the worker dispatches.

```python
# modules/exams/routes.py
@router.post("/exams/{exam_id}/generate", status_code=202)
async def generate(exam_id: UUID, idem_key: str = Header(..., alias="Idempotency-Key"),
                  user: User = Depends(get_current_user), enq: Enqueuer = Depends()):
    exam = await exam_service.get(user.id, exam_id)
    job = await ai_job_service.create(
        owner_id=user.id, job_type="question_generation",
        idempotency_key=idem_key,
        input_payload={"exam_id": str(exam_id)},
    )
    await enq.enqueue("ai:generation", {"ai_job_id": str(job.id)})
    return {"ai_job": ai_job_dto(job, poll_url=f"/api/v1/ai-jobs/{job.id}")}
```

The **worker** (`workers/ai_worker.py`) is a separate process running the same code:

```python
# workers/ai_worker.py
import asyncio
from bullmq import Worker
from app.ai.tasks import run_generation, run_grading

async def main():
    Worker("ai:generation", lambda job: run_generation(job.data["ai_job_id"]))
    Worker("ai:grading",    lambda job: run_grading(job.data["ai_job_id"]))
    await asyncio.Event().wait()
```

Inside `ai/tasks/generation.py`:
1. Mark `ai_job.status = processing`, set `started_at`.
2. Read exam + (optional) source from MinIO.
3. Call `provider.generate_structured(...)` (in-process).
4. Persist `QUESTION`s + `EXAM.answer_key` + `EXAM.questions_pdf_file_id/answers_pdf_file_id`.
5. Mark `ai_job.status = done`, persist `cost_usd_micro`, `tokens_*`.

**Idempotency:** `ai_job.idempotency_key` is `UNIQUE (owner_id, key)`. On retry, BullMQ re-delivers; the task checks the existing row's status and short-circuits if already `done`.

---

## 7. File handling (MinIO)

All binary uploads go through **presigned URLs**.

```python
# modules/uploads/routes.py
@router.post("/uploads/presign")
async def presign(req: PresignReq, user: User = Depends(get_current_user)):
    key = f"{req.kind.value}/{user.id}/{uuid7()}/{req.filename}"
    url = minio.presigned_put_object(BUCKET, key, expires=timedelta(minutes=10))
    return {"upload_url": url, "storage_key": key, "method": "PUT",
            "headers": {"Content-Type": req.mime_type}}
```

After the client PUTs the bytes, the calling endpoint takes `storage_key` (or `file_asset_id` if the file was already registered). Downloads use presigned GET URLs (5 min TTL).

**Naming:** the teacher sees `original_name`; renaming a file updates `file_asset.original_name` only — the MinIO object key is unchanged.

**Cleanup:** soft-deleted `file_asset` rows have their MinIO objects deleted by a daily cleanup task (P2; MVP leaves them).

---

## 8. PDF generation

WeasyPrint renders HTML templates to PDF.

```
storage/
  pdf_renderer.py        # WeasyPrint wrapper
  templates/
    questions.html.jinja
    answers.html.jinja
```

- **Questions PDF:** prompts + choices + max_score; no answers.
- **Answers PDF:** questions + correct answer + rubric + max_score; layout differs (page header "Answer Key").

Rendered on demand (and cached in MinIO as a `file_asset` so re-downloads are fast).

---

## 9. Excel import

`storage/excel_parser.py` reads `.xlsx` via `openpyxl`. The drag-to-map flow:

```python
# modules/students/routes.py
@router.post("/students/import/preview")
async def preview(file: UploadFile, user: User = Depends(get_current_user)):
    wb = load_workbook(file.file, read_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    samples = list(islice(ws.iter_rows(min_row=2, max_row=6, values_only=True), 5))
    return {
        "columns": [
            {"letter": get_column_letter(i + 1), "header": h, "sample_values": list(s)}
            for i, (h, s) in enumerate(zip(headers, zip(*samples)))
        ],
        "row_count": ws.max_row - 1,
    }

@router.post("/students/import", idempotency_key_required=True)
async def do_import(file: UploadFile, mapping: MappingReq,
                    idem_key: str = Header(...), user: User = Depends(get_current_user)):
    # Map each row by the column letter mapping → Student row.
    # Required: mapping.name column present.
    # Store unmapped columns under student.extra_columns.
    ...
```

---

## 10. Configuration & secrets

- **12-factor:** all config from env (`api/config.py` reads via `pydantic-settings`).
- **Secrets:** Google OAuth credentials, JWT signing key, AI provider key, MinIO access/secret — loaded from env in dev, from a vault in production.
- **AI provider key lives only in the API/worker environment.** The active provider is `AI_PROVIDER` env (default `minimax`); the default adapter reads `MINIMAX_API_KEY`.
- **Per-user settings** (e.g. default confidence threshold) live in `user.settings` JSONB.

---

## 11. Testing strategy

| Layer | Tool | Covers |
|---|---|---|
| **Unit** | pytest | services, mappers, AI structured validation |
| **Integration** | pytest + **Testcontainers (Postgres + MinIO + Redis)** | repositories + services end-to-end |
| **Owner isolation** | dedicated suite | cross-owner reads return zero rows; cross-owner writes raise ConflictError |
| **Contract** | schemathesis against the OpenAPI | every endpoint matches shapes + status codes + error codes |
| **AI eval** | `ai/eval/runner.py` | golden sets block regressions |
| **Load** | k6 | exam-season burst on `/ai-jobs/:id` and `POST /exams/:id/generate` |

> **Owner-isolation tests are non-negotiable** and gate merges.

---

## 12. Observability hooks

- **OpenTelemetry** auto-instrumentation in FastAPI + SQLAlchemy + httpx.
- **Every log line** carries `trace_id`, `owner_id`, `service`. **No student PII / answer content** in logs.
- **AI metrics:** `ai_job.count{type,status,model}`, `ai_job.tokens_*`, `ai_job.cost_usd_micro`, `ai_job.flagged_rate`. See [OBSERVABILITY.md](./OBSERVABILITY.md).

---

## 13. Resolved choices

- **ORM:** **SQLAlchemy 2.x + Alembic** (async `AsyncSession`). Composite FKs, JSONB ops, and explicit control outweigh SQLModel's reduced boilerplate at this scope.
- **Async queue:** **BullMQ via `python-bullmq`** + Redis. Same broker the JS side (Next.js dev tooling, future WebSocket fan-out) uses. Durable; retries handled by BullMQ; idempotency handled by `ai_job.idempotency_key`.
- **MinIO client:** **`minio-py`** wrapped in `asyncio.to_thread` (sync SDK is mature; thread offload is simpler than `aiobotocore`).
- **PDF generation:** **WeasyPrint** (HTML → PDF via Jinja templates in `storage/templates/`).
- **Excel parsing:** **openpyxl** for both preview and import (`storage/excel_parser.py`).