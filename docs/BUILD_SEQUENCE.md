# Build Sequence — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [PRD.md](./PRD.md) · [ARCHITECTURE.md](./ARCHITECTURE.md) · [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)
> **Consumed by:** implementers

The execution plan. The MVP is six **vertical slices** (M0–M5); each one ships a working app behind a feature flag and has tests + deployable artifacts.

---

## M0 — Skeleton & auth

**Outcome:** a teacher can sign in with Google and land on an empty dashboard.

**Includes**
- Monorepo layout: `api/`, `web/`, `storage/` (MinIO compose), `docs/`.
- Docker Compose: `postgres`, `redis`, `minio`, `api`, `web`, `ai-worker`.
- FastAPI: `/livez`, `/readyz`, `/auth/google`, `/auth/google/callback`, `/auth/refresh`, `/auth/logout`, `/me`.
- Next.js: `/login`, `/dashboard` (empty), root layout + providers, auth bootstrap, `useCurrentUser`.
- Alembic initial migration: `user`, `google_token`.
- Seed: empty DB (no fixtures).
- CI: lint, unit tests, owner-isolation test scaffold.
- Docs: this README + every doc under `docs/` is implementation-ready.

**Definition of Done**
- Sign-in flow end-to-end against a running compose stack.
- `/me` returns the user; refresh rotates the cookie.
- All CI checks green.

---

## M1 — Subjects, classes, students

**Outcome:** the teacher can manage subjects, classes, and students.

**Includes**
- Tables: `subject`, `class`, `class_subject`, `student`, `class_enrollment`.
- Routes: `/subjects`, `/classes`, `/students` (CRUD), `/classes/:id/subjects`, `/classes/:id/enrollments`.
- Web pages: `/subjects`, `/classes`, `/students`, `/classes/:id`.
- Components: `<SubjectsTable>`, `<ClassesTable>`, `<StudentsTable>`, `<NewSubjectDialog>`, `<NewClassDialog>`, `<NewStudentDialog>`, `<SubjectAssignDialog>`.
- Seed: 4 subjects + 2 classes + 30 students (see [MOCK_DATA.md](./MOCK_DATA.md)).
- Tests: owner-isolation suite expanded to cover new tables.

**Definition of Done**
- Create / list / edit / delete subjects, classes, students.
- Assign subjects to classes; enroll students.
- All entities scoped to owner; CI passes.

---

## M2 — Exams, questions, files, PDFs

**Outcome:** the teacher can author exams (manually), upload source images/PDFs, and download questions/answers PDFs.

**Includes**
- Tables: `exam`, `question`, `question_option`, `file_asset`.
- Routes: `/exams`, `/exams/:id`, `/exams/:id/questions`, `/exams/:id/files`, `/uploads/presign`, `/exams/:id/files/:fid/download`, `/exams/:id/pdf/questions`, `/exams/:id/pdf/answers`.
- Web pages: `/exams`, `/exams/:id`, `/exams/:id/questions`, `/exams/:id/files`.
- Components: `<ExamsTable>`, `<QuestionEditorDialog>`, `<QuestionReviewList>` (manual mode only), `<FileAssetTable>`, `<FileUploader>`, `<PdfDownloadButton>`.
- Storage: MinIO client + presigned URLs.
- PDF rendering: WeasyPrint templates for questions and answers.
- Tests: file upload flow + owner scoping on `file_asset`.

**Definition of Done**
- Create exam (manual only at this stage), add questions, upload source, rename files, download both PDFs.
- Source image/PDF renders in the UI preview.

---

## M3 — AI question generation

**Outcome:** the teacher triggers AI generation from text/image/PDF source; reviews and publishes.

**Includes**
- AI module: `AIProvider` port + MiniMax adapter (`ai/`; OpenAI SDK pointed at `https://api.minimax.io/v1`).
- BullMQ: queue + worker process.
- Routes: `/exams/:id/generate` (202), `/ai-jobs/:id` (poll), `/exams/:id/questions/:qid/approve|reject`, `/exams/:id/publish`.
- Web: `/exams/new` wizard (steps 1–7), `<AiJobProgress>`, `<QuestionReviewList>` (AI mode).
- Components: `<ExamWizard>`, `<SourceUploader>` (image/PDF), `<ExamConfigForm>`.
- AI evaluation: golden sets for at least one subject.
- Tests: structured-output validation; idempotency on AI jobs; provider error mapping.

**Definition of Done**
- Generate from text-only, from image, and from PDF source.
- Questions land in `in_review`; teacher edits/approves; exam publishes.
- AI eval gate blocks a regression in CI.

---

## M4 — Excel student import

**Outcome:** the teacher imports any `.xlsx` layout via drag-to-map.

**Includes**
- Routes: `/students/import/preview`, `/students/import`.
- Web: `/students/import` (3-step wizard), `<ColumnMapper>`.
- Storage: `excel_parser.py` (openpyxl).
- Tests: header detection, mapping validation, idempotency.

**Definition of Done**
- Upload `.xlsx` → preview detected columns + sample rows.
- Drag headers onto `name` (required) and optional fields → submit → students created.
- Extra columns persist in `student.extra_columns`.

---

## M5 — Grading runs

**Outcome:** the teacher runs AI grading per student, reviews flagged items, and finalizes with a CSV export.

**Includes**
- Tables: `grading_run`, `grading_item`, `grading_item_response`.
- Routes: `/grading-runs`, `/grading-runs/:id`, `/grading-runs/:id/items` (file upload), `/grading-runs/:id/items/:itemId`, `/grading-runs/:id/items/:itemId/responses/:rid` (override), `/grading-runs/:id/items/:itemId/waive-flag`, `/grading-runs/:id/finalize`, `/grading-runs/:id/results.csv`.
- Web: `/grading`, `/grading/new`, `/grading/:id`, `/grading/:id/items/:itemId`.
- Components: `<BenchmarkChoice>`, `<StudentAnswerUpload>`, `<GradingItemsTable>`, `<ResponsesTable>`, `<FinalizeGuard>`, `<ResultsCsvDownload>`.
- AI module: `grade.upload` task; benchmark extraction (PDF/image → answer key); confidence + flagging logic.
- Tests: finalize gate blocks when flagged items remain; override persists; CSV export.

**Definition of Done**
- Create grading run, upload per-student answers, AI grades each, flagged items appear for review.
- Override saves; finalize gated by review; CSV exports per-student totals.
- AI-down fallback: manual entry path works without AI.

---

## M6 — Polish (no scope additions)

**Outcome:** rough edges fixed before launch.

- Empty states everywhere.
- Error toasts + problem-detail mapping verified.
- Accessibility audit (keyboard nav, focus rings, color contrast).
- Performance pass (RSC where helpful, image lazy-loading).
- E2E happy-path test (sign in → create exam → generate → publish → grade → finalize).
- Backup & restore runbook.
- OpenAI / Vertex adapters stubbed (ADR-009 compliance — only MiniMax is fully wired).

---

## Slice dependency graph

```
M0 ──► M1 ──► M2 ──► M3 ──► M5
                │            ▲
                └────► M4 ───┘
                              │
                              └─► M6 (polish)
```

---

## Open items

- **M0 stack choices to finalize:** SQLAlchemy 2.x + Alembic (vs. SQLModel), BullMQ Python client vs. in-process queue. Recommend the safe defaults in [BACKEND_CONVENTIONS.md](./BACKEND_CONVENTIONS.md) §13.
- **M3 eval suite size:** start with 5 fixtures per question_type; grow as overrides accumulate.