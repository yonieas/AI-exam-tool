# Product Requirements Document — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Draft v1.0 (slim scope — single teacher)
> **Last updated:** 2026-06-18
> **Owner:** Product
> **Related docs:** [ERD.md](./ERD.md) · [ARCHITECTURE.md](./ARCHITECTURE.md) · [API_CONTRACT.md](./API_CONTRACT.md)

---

## 1. Overview

### 1.1 Problem
Teachers spend hours each week authoring exams (questions + answer keys) and grading student submissions — especially when answers are handwritten or scanned. Generic form tools don't generate content; LMS suites are oversized and tied to a school subscription the user doesn't have.

### 1.2 Product
A focused web app for a **single teacher** that:
1. Generates exam questions + answer keys from a subject and units (or an uploaded image/PDF source).
2. Saves generated exams and lets the teacher download **separate** questions and answers PDFs (with rename).
3. Imports student lists from any Excel format (flexible column mapping).
4. Grades uploaded student answers against a benchmark (AI-generated answers, or an uploaded benchmark PDF/image) with confidence flags.
5. Manages multiple classes and subjects.

### 1.3 Stack & shape
- **Backend:** Python + FastAPI modular monolith (single process). All AI calls run in-process via the `AIProvider` port (default: MiniMax via the OpenAI-compatible API).
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind. One portal (teacher).
- **Storage:** PostgreSQL 16 (data), MinIO (file assets), Redis (sessions + job queue).

### 1.4 Non-goals (v1)
- Multi-teacher collaboration or per-school isolation
- Parent/student portals, admission pipelines, attendance, timetable, gradebook/report cards
- Fee billing / invoicing / payments
- Real-time proctoring, plagiarism detection, adaptive practice
- Native mobile apps
- SSO/SAML/SCIM

### 1.5 Constraints
- **Modular monolith for easy feature growth** (per user requirement) — clear module boundaries so new features slot in without rewrite.
- **AI is assistive, never unauditable:** generated questions land in a review queue; AI grades include a confidence score and are teacher-overridable; low-confidence items are flagged before finalization.
- **Untrusted uploads:** any uploaded image/PDF is untrusted input to the AI — structured-output-only, no tools, no secrets in context (AI_SUBSYSTEM_SPEC §3).
- **Owner-scoped data:** every tenant-owned table has `owner_id`; queries filter by `current_user.id`. No cross-owner access.

---

## 2. Persona

| Persona | Role | Goals |
|---|---|---|
| **Ms. Alvarez** — High school science teacher | Sole primary user | Create exams fast, grade fairly, manage several classes |

The app supports one signed-in teacher at a time. The teacher's identity is a Google account; all classes/subjects/exams/students/grading runs they create are owned by that account.

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Subject** | A taught topic (e.g. Physics, Biology, Mathematics). |
| **Unit** | A sub-topic within a subject (e.g. "Newton's Laws", "Photosynthesis"). |
| **Class** | A named group of students taught together (e.g. "Grade 10-A"). |
| **Exam** | A generated or hand-authored assessment scoped to one subject. |
| **Question** | A single MCQ, essay, or other item with prompt + answer key + max score. |
| **Answer key** | The benchmark answers for an exam (AI-generated, or uploaded as PDF/image). |
| **Grading run** | A grading session for one exam: per-student answer upload → AI grade → optional teacher override → finalize. |
| **File asset** | A blob in MinIO: source image/PDF, generated PDF, student answer upload, benchmark upload. |
| **AI job** | An async AI task (generation or grading) tracked in a job queue. |

---

## 4. Functional requirements

Stable `FR-x.y` IDs. Priorities: **Must** (MVP), **Could** (later).

### 4.1 Authentication
| ID | Requirement | Priority |
|---|---|---|
| FR-AUTH.1 | Sign in with Google OAuth (no password). | Must |
| FR-AUTH.2 | Session is a JWT (access + rotating refresh); refresh via HttpOnly cookie. | Must |
| FR-AUTH.3 | Sign out revokes the session. | Must |

### 4.2 Subjects & classes
| ID | Requirement | Priority |
|---|---|---|
| FR-SC.1 | Create/list/rename/delete **subjects** (Physics, Biology, Chemistry, Math, …; extensible). | Must |
| FR-SC.2 | Create/list/rename/delete **classes** (e.g. "Grade 10-A"). | Must |
| FR-SC.3 | Assign one or more subjects to a class; a class's subject list drives which subjects can host an exam for that class. | Must |
| FR-SC.4 | A class has many students (enrollment). | Must |

### 4.3 Students
| ID | Requirement | Priority |
|---|---|---|
| FR-S.1 | Add a single student manually (name + optional fields). | Must |
| FR-S.2 | **Import students from Excel (`.xlsx`)** with arbitrary column layout — the teacher maps detected columns onto canonical fields (`name`, `student_id`, `email`, plus any extra columns stored as-is). | Must |
| FR-S.3 | List, rename, delete students. | Must |
| FR-S.4 | Enroll/unenroll a student in a class. | Must |

### 4.4 Exam creation
| ID | Requirement | Priority |
|---|---|---|
| FR-E.1 | Start an exam by picking: subject (from configured list), one or more **units** (free-text), total question count, question type mode (`mcq` / `essay` / `both`; in `both` mode the teacher splits the count). | Must |
| FR-E.2 | Optional **source input**: none, an uploaded **image** (photo of textbook page), or an uploaded **PDF** (reference). | Must |
| FR-E.3 | AI generates questions + answer keys from the subject/units, optionally grounded in the uploaded source. Each question has prompt, type, options/answer key, max score. | Must |
| FR-E.4 | Generated questions land in a **review queue**: the teacher edits or approves before the exam is published. | Must |
| FR-E.5 | Manual question entry (without AI) is supported: teacher types questions one by one. | Could |

### 4.5 Exam files & download
| ID | Requirement | Priority |
|---|---|---|
| FR-F.1 | Save the exam (questions + answer key) as file assets in MinIO. | Must |
| FR-F.2 | The teacher can **rename** each file asset (questions bundle, answers bundle, source image/PDF) before download. | Must |
| FR-F.3 | Download **separate** PDFs: one with questions only, one with answers only. | Must |
| FR-F.4 | Download the original source image/PDF as-is. | Must |

### 4.6 Grading
| ID | Requirement | Priority |
|---|---|---|
| FR-G.1 | Create a **grading run** for an exam: choose the benchmark answer key (the AI-generated key from `FR-E.3`, or upload a separate benchmark PDF/image). | Must |
| FR-G.2 | Upload one answer file (image/PDF) per student. | Must |
| FR-G.3 | AI grades each student submission against the benchmark, returning per-question `awarded_score`, `max_score`, `confidence`, and a `flagged` flag for low-confidence items. | Must |
| FR-G.4 | Items with confidence below a threshold (or flagged for handwriting/OCR issues) require **teacher review** before the run can be finalized. | Must |
| FR-G.5 | The teacher can **override** any AI score; overrides are recorded with the original AI score for audit. | Must |
| FR-G.6 | Finalize the run: write final scores to a results table; provide a downloadable CSV of per-student totals. | Must |
| FR-G.7 | AI down → the run is still saved; teacher can manually enter scores per student and finalize. | Should |

### 4.7 Async AI
| ID | Requirement | Priority |
|---|---|---|
| FR-AI.1 | Generation and grading endpoints return `202 + ai_job` immediately; the client polls job status. | Must |
| FR-AI.2 | AI jobs are **idempotent** (idempotency key) — no double-generation/double-grading on retry. | Must |
| FR-AI.3 | AI provider is configurable behind an `AIProvider` port (default MiniMax). | Must |
| FR-AI.4 | AI calls use **structured output only** (`output_config.format.json_schema`); scores are clamped server-side to `[0, max_score]`. | Must |

---

## 5. User journeys (happy path)

### 5.1 First-time setup
1. Ms. Alvarez signs in with Google (FR-AUTH.1).
2. She adds subjects: Physics, Biology, Chemistry, Mathematics (FR-SC.1).
3. She creates class "Grade 10-A" and assigns all four subjects (FR-SC.2/3).
4. She imports students via Excel upload → drag-to-map → save (FR-S.2).

### 5.2 Create & download an exam
1. Ms. Alvarez clicks **New Exam**, picks subject=Physics, units=["Kinematics","Forces"], count=10, type=both (7 MCQ + 3 essay) (FR-E.1).
2. She uploads a photo of a textbook page as the source (FR-E.2).
3. AI generates 10 questions + an answer key (FR-E.3); questions appear in the review queue (FR-E.4).
4. She edits 2 questions, approves the rest.
5. She renames the files (e.g. `physics_kinematics_q.pdf`, `physics_kinematics_a.pdf`) (FR-F.2).
6. She downloads both PDFs separately (FR-F.3).

### 5.3 Grade the exam
1. She creates a grading run for the exam, using the AI-generated key as the benchmark (FR-G.1).
2. She uploads one answer file per student (FR-G.2).
3. AI grades each student; 3 items are flagged for review (FR-G.3/G.4).
4. She reviews and overrides the 3 flagged scores, finalizes the run (FR-G.5/G.6).
5. She downloads the results CSV.

---

## 6. Non-functional requirements

| Category | Requirement |
|---|---|
| **Performance** | p95 page TTFB < 400 ms; p95 API < 300 ms (non-AI). AI generation p95 < 30 s/batch (async). AI grading p95 < 20 s/submission (async). |
| **Security** | TLS 1.2+ in transit. AES-256 at rest. OWASP ASVS L2. |
| **AI safety** | Uploaded source/student content is untrusted input. Structured-output-only. No tools, no secrets in the model context. Scores clamped to `[0, max_score]`. AI results are teacher-overridable. Low-confidence items flagged before finalization. |
| **Reliability** | RPO ≤ 5 min, RTO ≤ 1 h. Backups + PITR. AI down → manual grading fallback (FR-G.7). |
| **Privacy** | No student PII in logs/traces (IDs + counts only). Student files are private to the teacher. |
| **Scalability** | Single teacher; design is horizontally scalable later (modular monolith keeps seams clear). |

---

## 7. Success metrics (MVP)

| Metric | Target |
|---|---|
| Time saved on exam authoring vs manual | ≥ 50% |
| Time saved on grading vs manual | ≥ 50% |
| AI grading agreement with teacher on objective items | ≥ 95% |
| AI-generated question acceptance rate (no edit needed) | ≥ 70% |
| AI job success rate | ≥ 99% |

---

## 8. Out of scope (later)

- Multi-teacher / per-school isolation
- Parent/student portals, messaging, announcements
- Gradebook, report cards, transcripts
- Fee/invoice/payment flows
- Admissions, attendance, timetable
- Plagiarism detection, proctored exam mode
- Native mobile apps
- Public REST API / webhooks / SSO

---

## 9. Open questions

- Confidence threshold default (suggest 0.7 on a 0–1 scale; configurable per exam later).
- Allow renaming of a published exam? (Decision: yes, free-form `title`; rename does not re-trigger AI.)
- Per-student answer upload: one file per student or batch? (Decision: one file per student for now; batch is P2.)
- Single-subject exam only, or multi-subject exams? (Decision: single subject.)