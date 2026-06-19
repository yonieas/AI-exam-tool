# Mock Data & Input Examples — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [DATABASE_SCHEMA.md §13](./DATABASE_SCHEMA.md) · [BUILD_SEQUENCE.md](./BUILD_SEQUENCE.md)

The coherent demo dataset used by the seed script and the E2E happy-path test.

---

## 1. Teacher

**Ms. Alvarez** — `teacher@demo.local`

- Google OAuth (`google_sub = "demo-google-sub-001"`)
- Avatar: demo avatar URL
- `settings`: `{ "default_confidence_threshold": 0.7 }`

---

## 2. Subjects (4)

| id (short) | name | code |
|---|---|---|
| subj-phys | Physics | PHYS |
| subj-bio | Biology | BIO |
| subj-chem | Chemistry | CHEM |
| subj-math | Mathematics | MATH |

---

## 3. Classes (2)

| id (short) | name | grade_level | subjects taught |
|---|---|---|---|
| cls-10a | Grade 10-A | 10 | all 4 |
| cls-11b | Grade 11-B | 11 | all 4 |

`class_subject` rows: each class × all 4 subjects (8 rows).

---

## 4. Students (30)

15 per class. Names borrowed from public domain lists; `student_code` is `S###`.

### 4.1 Grade 10-A (15)

| student_code | name | email |
|---|---|---|
| S001 | Aarav Singh | aarav@demo.local |
| S002 | Bea Costa | bea@demo.local |
| S003 | Cira Lopez | cira@demo.local |
| S004 | Daichi Ito | daichi@demo.local |
| S005 | Elena Popov | elena@demo.local |
| S006 | Finn O'Brien | finn@demo.local |
| S007 | Gita Rao | gita@demo.local |
| S008 | Hugo Martin | hugo@demo.local |
| S009 | Iris Nakata | iris@demo.local |
| S010 | Jamal Ahmed | jamal@demo.local |
| S011 | Kira Park | kira@demo.local |
| S012 | Leo Ferrari | leo@demo.local |
| S013 | Maya Devi | maya@demo.local |
| S014 | Niko Vargas | niko@demo.local |
| S015 | Omar Bashir | omar@demo.local |

### 4.2 Grade 11-B (15)

| student_code | name | email |
|---|---|---|
| S101 | Pia Mendez | pia@demo.local |
| S102 | Quentin Lee | quentin@demo.local |
| S103 | Rina Suzuki | rina@demo.local |
| S104 | Sami Cohen | sami@demo.local |
| S105 | Tina Olsen | tina@demo.local |
| S106 | Uri Patel | uri@demo.local |
| S107 | Vera Hofmann | vera@demo.local |
| S108 | Wes Adekunle | wes@demo.local |
| S109 | Xena Volkov | xena@demo.local |
| S110 | Yara Saade | yara@demo.local |
| S111 | Zane Wei | zane@demo.local |
| S112 | Ana Becker | ana@demo.local |
| S113 | Boris Klein | boris@demo.local |
| S114 | Cleo Hart | cleo@demo.local |
| S115 | Dani Romero | dani@demo.local |

`extra_columns`: empty for all seeded students (a few have `{"homeroom": "10A"}` to demo the Excel import's `extra_columns` path).

---

## 5. Demo exams (3)

| id (short) | title | subject | units | mode | counts | source | status |
|---|---|---|---|---|---|---|---|
| exam-phys-1 | Physics — Kinematics | Physics | ["Kinematics","Forces"] | both | 5 mcq + 2 essay | none | published |
| exam-bio-1 | Biology — Cells | Biology | ["Cell structure","Photosynthesis"] | mcq | 8 | image | in_review |
| exam-chem-1 | Chemistry — Reactions | Chemistry | ["Acids","Bases"] | essay | 3 | pdf | draft |

- **exam-phys-1** has 7 questions, an `answer_key` JSON, and PDF file assets (`questions.pdf`, `answers.pdf`) — used for the demo download flow.
- **exam-bio-1** has 8 AI-generated questions pending review (status `in_review`) — used for the wizard's review-queue step.
- **exam-chem-1** has 0 questions (status `draft`) — used to demo the "before generation" state.

---

## 6. Demo grading run (1)

`run-phys-1-3`:

- `exam_id` = `exam-phys-1`
- `benchmark_kind` = `exam_answer_key` (uses `exam-phys-1.answer_key`)
- `status` = `needs_review`
- 15 `grading_item`s (one per Grade 10-A student)
- 3 items flagged (S003, S009, S014) — AI confidence < 0.7 on handwriting
- 2 items finalized (S001, S002)

This run demonstrates the review queue and the finalize gate (blocked until all flagged items are reviewed or waived).

---

## 7. Excel import fixture (sample.xlsx)

Saved at `storage/fixtures/students_sample.xlsx`. Three sheets (we use the first).

| Student Name | Student ID | Email | Homeroom |
|---|---|---|---|
| Aarav Singh | S001 | aarav@demo.local | 10A |
| Bea Costa | S002 | bea@demo.local | 10A |
| Cira Lopez | S003 | cira@demo.local | 10A |
| ... | ... | ... | ... |

Used by the M4 import wizard. The drag-to-map step assigns:
- `Student Name` → `name` (required)
- `Student ID` → `student_code`
- `Email` → `email`
- `Homeroom` → `extra_columns.homeroom`

---

## 8. Seed script location

`api/scripts/seed.py` — idempotent (uses upserts on natural keys like `user.email`, `subject.name` per owner). Run with `python -m app.scripts.seed` after `alembic upgrade head`.

---

## 9. Open items

- **Realistic student photos:** seed uses initials only; no photo URLs.
- **Demo answer files:** a single sample PDF in `storage/fixtures/answer_sample.pdf` is reused for all 15 grading_items in `run-phys-1-3` (a real demo would have 15 distinct files; for the seed we reuse the same to keep the seed deterministic).