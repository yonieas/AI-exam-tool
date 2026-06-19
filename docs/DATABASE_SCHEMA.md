# Physical Database Schema — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0 — MVP scope
> **Datastore:** PostgreSQL 16
> **Last updated:** 2026-06-18
> **Derives from:** [ERD.md](./ERD.md) · [ARCHITECTURE.md §5](./ARCHITECTURE.md) · [AUTH.md](./AUTH.md)
> **Consumed by:** [API_CONTRACT.md](./API_CONTRACT.md) · [BACKEND_CONVENTIONS.md](./BACKEND_CONVENTIONS.md)

This is the **physical** schema: column types, full enum value lists, indexes, triggers, and seed data for the entity set in [ERD.md](./ERD.md). The runtime DB role (`app_runtime`) is **not** `BYPASSRLS`; multi-tenancy is enforced at the application layer via `owner_id` filters, not RLS — see [AUTH.md §3](./AUTH.md).

---

## 1. Scope

Tables in this document (all MVP):

| Subdomain | Tables |
|---|---|
| Identity | `user`, `google_token` |
| Subjects & Classes | `subject`, `class`, `class_subject`, `student`, `class_enrollment` |
| Exams & Questions | `exam`, `question`, `question_option` |
| Grading | `grading_run`, `grading_item`, `grading_item_response` |
| Files | `file_asset` |
| Async AI | `ai_job` |

> The logical `EXAM.answer_key` (JSONB) holds the benchmark answers inline; a `FILE_ASSET` row mirrors it as a downloadable PDF.

---

## 2. Conventions (physical)

- **Primary keys:** `id UUID PRIMARY KEY DEFAULT uuid_generate_v7()` (ADR-007).
- **Tenant column:** every tenant-owned table has `owner_id UUID NOT NULL REFERENCES user(id)`.
- **Timestamps:** `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (trigger-maintained). Auditable tables add `created_by UUID`, `updated_by UUID` → `user(id)`.
- **Soft delete:** `deleted_at TIMESTAMPTZ NULL`; default queries filter `deleted_at IS NULL`.
- **Enums:** native Postgres `ENUM` (see §5). Adding a value is `ALTER TYPE … ADD VALUE` (non-breaking).
- **JSONB:** used for variable payloads (answer keys, question options, AI metadata, Excel extras).
- **FK on delete:** default `ON DELETE RESTRICT`. Owned children use `ON DELETE CASCADE`.
- **Composite tenant FKs:** child rows referencing an `owner_id`-bearing parent carry `(parent_id, owner_id)` with a unique on the parent's `(id)` — defense-in-depth.

---

## 3. Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
```

---

## 4. Helper functions

### 4.1 UUID v7 generator

```sql
-- Same as ADR-007 fallback; on PG18+ replace with native uuidv7().
CREATE OR REPLACE FUNCTION uuid_generate_v7()
RETURNS uuid LANGUAGE plpgsql VOLATILE AS $$
DECLARE
  unix_ts_ms bytea;
  uuid_bytes bytea;
BEGIN
  unix_ts_ms = substring(int8send((extract(epoch FROM clock_timestamp()) * 1000)::bigint) FROM 3);
  uuid_bytes = unix_ts_ms || gen_random_bytes(10);
  uuid_bytes = set_byte(uuid_bytes, 6, (b'0111' || get_byte(uuid_bytes, 6)::bit(4))::bit(8)::int);
  uuid_bytes = set_byte(uuid_bytes, 8, (b'10'  || get_byte(uuid_bytes, 8)::bit(6))::bit(8)::int);
  RETURN encode(uuid_bytes, 'hex')::uuid;
END
$$;
```

### 4.2 `updated_at` trigger

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END
$$;
```

### 4.3 Composite FK helper

For child rows that must match the parent's `owner_id`:

```sql
-- Add a unique index on the parent (id, owner_id):
CREATE UNIQUE INDEX uq_subject_owner ON subject(id, owner_id);
-- Then the child references both:
ALTER TABLE exam
  ADD CONSTRAINT fk_exam_subject_owner
  FOREIGN KEY (subject_id, owner_id)
  REFERENCES subject(id, owner_id)
  ON DELETE RESTRICT;
```

---

## 5. Enum types

```sql
-- Identity
-- (no enums for user/google_token; plain strings + citext)

-- Subjects & Classes
CREATE TYPE question_type_mode AS ENUM ('mcq','essay','both');
CREATE TYPE exam_source_kind   AS ENUM ('none','image','pdf');

-- Exams & Questions
CREATE TYPE exam_status        AS ENUM ('draft','in_review','published','closed');
CREATE TYPE question_type      AS ENUM ('mcq','essay');
CREATE TYPE question_status    AS ENUM ('draft','in_review','approved');

-- Grading
CREATE TYPE benchmark_kind     AS ENUM ('exam_answer_key','uploaded');
CREATE TYPE grading_run_status AS ENUM ('draft','grading','needs_review','finalized');
CREATE TYPE grading_item_status AS ENUM ('pending','ai_processing','ai_done','reviewed','final');

-- Files
CREATE TYPE file_asset_kind    AS ENUM (
  'source_image','source_pdf',
  'questions_pdf','answers_pdf',
  'benchmark_pdf','benchmark_image',
  'student_answer'
);

-- Async AI
CREATE TYPE ai_job_type        AS ENUM ('question_generation','grading');
CREATE TYPE ai_job_status      AS ENUM ('queued','processing','done','failed');
CREATE TYPE ai_provider        AS ENUM ('minimax'); -- extend when a new adapter is certified (ADR-009)
```

---

## 6. Identity

### 6.1 `user` (the teacher)

```sql
CREATE TABLE "user" (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  email           CITEXT NOT NULL,
  full_name       TEXT NOT NULL,
  avatar_url      TEXT,
  settings        JSONB NOT NULL DEFAULT '{}',
  last_login_at   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ,
  CONSTRAINT uq_user_email UNIQUE (email)
);
CREATE TRIGGER trg_touch_user BEFORE UPDATE ON "user"
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

> Single role (teacher). No `role` / `permission` / `membership` tables. The OAuth callback creates the row on first sign-in.

### 6.2 `google_token`

```sql
CREATE TABLE google_token (
  id                       UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  user_id                  UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  google_sub               TEXT NOT NULL,
  access_token_encrypted   BYTEA NOT NULL,
  refresh_token_encrypted  BYTEA NOT NULL,
  access_token_expires_at  TIMESTAMPTZ NOT NULL,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_google_token_sub UNIQUE (google_sub)
);
CREATE TRIGGER trg_touch_google_token BEFORE UPDATE ON google_token
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 7. Subjects & Classes

### 7.1 `subject`

```sql
CREATE TABLE subject (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id    UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  code        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ,
  CONSTRAINT uq_subject_owner_name UNIQUE (owner_id, name)
);
CREATE UNIQUE INDEX uq_subject_owner ON subject(id, owner_id);
CREATE TRIGGER trg_touch_subject BEFORE UPDATE ON subject
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 7.2 `class`

```sql
CREATE TABLE class (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id     UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  grade_level  INT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ,
  CONSTRAINT uq_class_owner_name UNIQUE (owner_id, name)
);
CREATE UNIQUE INDEX uq_class_owner ON class(id, owner_id);
CREATE TRIGGER trg_touch_class BEFORE UPDATE ON class
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 7.3 `class_subject` (M:N)

```sql
CREATE TABLE class_subject (
  class_id    UUID NOT NULL,
  subject_id  UUID NOT NULL,
  owner_id    UUID NOT NULL, -- denormalized for uniform queries
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (class_id, subject_id),
  FOREIGN KEY (class_id, owner_id)   REFERENCES class(id,   owner_id) ON DELETE CASCADE,
  FOREIGN KEY (subject_id, owner_id) REFERENCES subject(id, owner_id) ON DELETE CASCADE
);
```

### 7.4 `student`

```sql
CREATE TABLE student (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id        UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  student_code    TEXT,
  email           CITEXT,
  extra_columns   JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ
);
CREATE INDEX ix_student_owner ON student(owner_id) WHERE deleted_at IS NULL;
CREATE TRIGGER trg_touch_student BEFORE UPDATE ON student
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 7.5 `class_enrollment`

```sql
CREATE TABLE class_enrollment (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id     UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  class_id     UUID NOT NULL,
  student_id   UUID NOT NULL,
  enrolled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ,
  CONSTRAINT uq_enrollment UNIQUE (class_id, student_id),
  FOREIGN KEY (class_id,   owner_id) REFERENCES class(id,   owner_id) ON DELETE CASCADE,
  FOREIGN KEY (student_id, owner_id) REFERENCES student(id, owner_id) ON DELETE CASCADE
);
CREATE INDEX ix_enrollment_student ON class_enrollment(student_id);
```

---

## 8. Exams & Questions

### 8.1 `exam`

```sql
CREATE TABLE exam (
  id                       UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id                 UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  subject_id               UUID NOT NULL,
  title                    TEXT NOT NULL,
  source_kind              exam_source_kind NOT NULL DEFAULT 'none',
  units                    JSONB NOT NULL DEFAULT '[]',          -- ["Kinematics","Forces"]
  question_type_mode       question_type_mode NOT NULL,
  total_count              INT NOT NULL CHECK (total_count > 0),
  mcq_count                INT CHECK (mcq_count >= 0),
  essay_count              INT CHECK (essay_count >= 0),
  generation_config        JSONB NOT NULL DEFAULT '{}',          -- language, difficulty
  source_file_id           UUID,
  answer_key               JSONB,                                -- structured Answer[]
  answer_key_file_id       UUID,
  questions_pdf_file_id    UUID,
  answers_pdf_file_id      UUID,
  status                   exam_status NOT NULL DEFAULT 'draft',
  ai_generated             BOOLEAN NOT NULL DEFAULT false,
  published_at             TIMESTAMPTZ,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at               TIMESTAMPTZ,
  CHECK (
    (question_type_mode = 'mcq'   AND mcq_count   = total_count AND essay_count IS NULL) OR
    (question_type_mode = 'essay' AND essay_count = total_count AND mcq_count   IS NULL) OR
    (question_type_mode = 'both'  AND mcq_count + essay_count = total_count)
  ),
  FOREIGN KEY (subject_id, owner_id) REFERENCES subject(id, owner_id) ON DELETE RESTRICT
);
CREATE INDEX ix_exam_owner_status ON exam(owner_id, status) WHERE deleted_at IS NULL;
CREATE INDEX ix_exam_subject ON exam(subject_id);
CREATE TRIGGER trg_touch_exam BEFORE UPDATE ON exam
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

> The CHECK enforces PRD FR-E.1: `mcq` ⇒ all MCQ; `essay` ⇒ all essay; `both` ⇒ counts sum to `total_count`.

### 8.2 `question`

```sql
CREATE TABLE question (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id    UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  exam_id     UUID NOT NULL,
  position    INT NOT NULL CHECK (position > 0),
  type        question_type NOT NULL,
  prompt      TEXT NOT NULL,
  options     JSONB NOT NULL DEFAULT '{}',  -- MCQ: {"choices":[{"label":"...","is_correct":true},...]}
  rubric      JSONB,                        -- essay: {"criteria":[{"label":"...","points":2},...]}
  max_score   NUMERIC(8,2) NOT NULL DEFAULT 1.0,
  ai_meta     JSONB,                        -- {"model":"...","source_citation":"...","confidence":0.9}
  status      question_status NOT NULL DEFAULT 'draft',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (exam_id, owner_id) REFERENCES exam(id, owner_id) ON DELETE CASCADE,
  CONSTRAINT uq_question_exam_position UNIQUE (exam_id, position)
);
CREATE INDEX ix_question_exam ON question(exam_id);
CREATE TRIGGER trg_touch_question BEFORE UPDATE ON question
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 8.3 `question_option`

```sql
CREATE TABLE question_option (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  question_id  UUID NOT NULL REFERENCES question(id) ON DELETE CASCADE,
  label        TEXT NOT NULL,
  is_correct   BOOLEAN NOT NULL DEFAULT false,
  position     INT NOT NULL CHECK (position >= 0),
  CONSTRAINT uq_option_question_position UNIQUE (question_id, position)
);
```

---

## 9. Grading

### 9.1 `grading_run`

```sql
CREATE TABLE grading_run (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id              UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  exam_id               UUID NOT NULL,
  benchmark_kind        benchmark_kind NOT NULL,
  benchmark_file_id     UUID,                  -- when benchmark_kind='uploaded'
  title                 TEXT NOT NULL,
  status                grading_run_status NOT NULL DEFAULT 'draft',
  max_score_total       NUMERIC(10,2) NOT NULL,
  finalized_at          TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at            TIMESTAMPTZ,
  FOREIGN KEY (exam_id, owner_id) REFERENCES exam(id, owner_id) ON DELETE RESTRICT
);
CREATE INDEX ix_grading_run_owner_status ON grading_run(owner_id, status) WHERE deleted_at IS NULL;
CREATE TRIGGER trg_touch_grading_run BEFORE UPDATE ON grading_run
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 9.2 `grading_item`

```sql
CREATE TABLE grading_item (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id          UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  grading_run_id    UUID NOT NULL,
  student_id        UUID NOT NULL,
  answer_file_id    UUID NOT NULL,
  status            grading_item_status NOT NULL DEFAULT 'pending',
  total_score       NUMERIC(10,2),           -- null until graded/final
  max_score_total   NUMERIC(10,2) NOT NULL,
  flagged           BOOLEAN NOT NULL DEFAULT false,
  finalized         BOOLEAN NOT NULL DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_grading_item_run_student UNIQUE (grading_run_id, student_id),
  FOREIGN KEY (grading_run_id, owner_id) REFERENCES grading_run(id, owner_id) ON DELETE CASCADE,
  FOREIGN KEY (student_id,     owner_id) REFERENCES student(id,     owner_id) ON DELETE RESTRICT
);
CREATE INDEX ix_grading_item_flagged ON grading_item(grading_run_id) WHERE flagged AND NOT finalized;
CREATE TRIGGER trg_touch_grading_item BEFORE UPDATE ON grading_item
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 9.3 `grading_item_response`

```sql
CREATE TABLE grading_item_response (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  grading_item_id     UUID NOT NULL REFERENCES grading_item(id) ON DELETE CASCADE,
  question_id         UUID NOT NULL REFERENCES question(id),
  answer_text         TEXT,
  ai_score            NUMERIC(8,2),
  max_score           NUMERIC(8,2) NOT NULL,
  teacher_score       NUMERIC(8,2),
  confidence          NUMERIC(4,3) CHECK (confidence >= 0 AND confidence <= 1),
  flagged             BOOLEAN NOT NULL DEFAULT false,
  ai_rationale        TEXT,
  teacher_rationale   TEXT,
  overridden          BOOLEAN NOT NULL DEFAULT false,
  graded_at           TIMESTAMPTZ,
  reviewed_at         TIMESTAMPTZ,
  CONSTRAINT uq_response_item_question UNIQUE (grading_item_id, question_id)
);
CREATE INDEX ix_response_question ON grading_item_response(question_id);
```

---

## 10. Files

### 10.1 `file_asset`

```sql
CREATE TABLE file_asset (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id            UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  exam_id             UUID,
  grading_run_id      UUID,
  grading_item_id     UUID,
  kind                file_asset_kind NOT NULL,
  storage_key         TEXT NOT NULL,        -- MinIO object key
  original_name       TEXT NOT NULL,        -- teacher-visible
  mime_type           TEXT NOT NULL,
  size_bytes          BIGINT NOT NULL CHECK (size_bytes >= 0),
  metadata            JSONB NOT NULL DEFAULT '{}',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at          TIMESTAMPTZ
);
CREATE INDEX ix_file_owner_exam ON file_asset(owner_id, exam_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_file_owner_kind ON file_asset(owner_id, kind);
```

> `original_name` is what the teacher sees; renaming the file updates this column (FR-F.2). The MinIO object is untouched on rename.

---

## 11. Async AI

### 11.1 `ai_job`

```sql
CREATE TABLE ai_job (
  id                     UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  owner_id               UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  job_type               ai_job_type NOT NULL,
  job_status             ai_job_status NOT NULL DEFAULT 'queued',
  exam_id                UUID,
  grading_run_id         UUID,
  grading_item_id        UUID,
  input_payload          JSONB NOT NULL,
  output_payload         JSONB,
  error                  TEXT,
  total_tokens_input     INT NOT NULL DEFAULT 0,
  total_tokens_output    INT NOT NULL DEFAULT 0,
  cost_usd_micro         BIGINT NOT NULL DEFAULT 0,
  idempotency_key        TEXT,
  queued_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at             TIMESTAMPTZ,
  completed_at           TIMESTAMPTZ,
  CONSTRAINT uq_ai_job_idem UNIQUE (owner_id, idempotency_key)
);
CREATE INDEX ix_ai_job_active
  ON ai_job(job_status) WHERE job_status IN ('queued','processing');
CREATE INDEX ix_ai_job_owner_queued
  ON ai_job(owner_id, queued_at DESC);
```

---

## 12. Composite tenant foreign keys (defense-in-depth)

For every child of an `owner_id`-bearing parent, the migration adds `(parent_id, owner_id) → parent(id, owner_id)` and the parent has a `UNIQUE (id, owner_id)` index. The application's repo layer also enforces `owner_id` equality; the constraint is a backstop. See [BACKEND_CONVENTIONS.md §3](./BACKEND_CONVENTIONS.md).

---

## 13. Seed data

For local dev and the demo tenant ([MOCK_DATA.md](./MOCK_DATA.md)):

- 1 user (Ms. Alvarez, `teacher@demo.local`)
- 4 subjects: Physics, Biology, Chemistry, Mathematics
- 2 classes: `Grade 10-A`, `Grade 11-B`
- `class_subject` rows: each class × all 4 subjects
- 30 students split across the two classes
- 3 demo exams (one per "physics/biology/chemistry") in `in_review` / `published` state
- 1 demo `grading_run` with 15 `grading_item`s and per-question responses

---

## 14. Migrations

- Alembic in `api/migrations/`. Forward-only. Expand/contract for breaking changes.
- One migration per logical change. Never edit a committed migration.

---

## 15. Open items for the team

- **Decimal precision:** `max_score` is `NUMERIC(8,2)` (up to 999,999.99). Sufficient for K-12 grades; tighten or widen if fractional rubrics become a thing.
- **Question banks:** not modeled at MVP. P2 if the teacher wants reuse.
- **Bulk-export:** not modeled. P2 (CSV export of grading results).