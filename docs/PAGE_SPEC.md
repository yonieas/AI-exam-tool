# Page Specification — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [PRD.md](./PRD.md) · [FRONTEND_ARCHITECTURE.md](./FRONTEND_ARCHITECTURE.md) · [API_CONTRACT.md](./API_CONTRACT.md)
> **Consumed by:** frontend implementation

Per-page assembly: route, components, data, permissions. All routes under the `(app)` route group require an authenticated session.

---

## 1. `/login`

**Route:** `/login`
**Auth:** public
**Purpose:** start Google OAuth

| Region | Component | Data |
|---|---|---|
| Centered card | `<Button variant="primary" size="lg">Continue with Google</Button>` | link → `GET /auth/google` |
| Footer | "By signing in, you agree to the terms." | static |

---

## 2. `/auth/callback`

**Route:** `/auth/callback`
**Auth:** public (handled by backend)
**Purpose:** capture the redirect from Google

- Backend handles the full `/auth/google/callback`; this client-side page is a stub that triggers the `GET /auth/refresh` and then `router.replace('/dashboard')`.

---

## 3. `/dashboard`

**Route:** `/dashboard`
**Auth:** any
**Purpose:** home — counts + quick actions + recent activity
**RSC:** yes (counts preloaded)

| Region | Component | Data |
|---|---|---|
| Heading | "Welcome back, {full_name}" | from `GET /me` |
| Stat grid | 4 `<StatCard>` (subjects, classes, students, exams) | `GET /me/dashboard` |
| Quick actions | 3 `<Button>` (New Exam, New Grading Run, Import Students) | links |
| Recent exams | `<ExamList>` last 5 | `GET /exams?limit=5` |
| Recent grading runs | `<GradingList>` last 5 | `GET /grading-runs?limit=5` |

---

## 4. `/subjects`

**Route:** `/subjects`
**Auth:** any

| Region | Component | Data |
|---|---|---|
| Header | "Subjects" + `<Button>New subject</Button>` | — |
| Table | `<SubjectsTable>` (name, code, exam count) | `GET /subjects` |
| New-subject dialog | `<NewSubjectDialog>` | `POST /subjects` |

---

## 5. `/subjects/:id`

| Region | Component | Data |
|---|---|---|
| Header | Subject name + actions (Rename, Delete) | `GET /subjects/:id` |
| Body | Stats: classes teaching this subject, exams in this subject | joined queries |
| Linked classes | `<ClassList>` | `GET /classes?subject_id=:id` |
| Exams | `<ExamList>` | `GET /exams?subject_id=:id` |

---

## 6. `/classes`

**Route:** `/classes`

| Region | Component | Data |
|---|---|---|
| Header | "Classes" + `<Button>New class</Button>` | — |
| Table | `<ClassesTable>` (name, grade, student count, subject count) | `GET /classes` |
| New-class dialog | `<NewClassDialog>` (name, grade_level, optional initial subject set) | `POST /classes` |

---

## 7. `/classes/:id`

| Region | Component | Data |
|---|---|---|
| Header | Class name + actions | `GET /classes/:id` |
| Subjects card | `<SubjectChip>` list + edit button → `<SubjectAssignDialog>` | `PUT /classes/:id/subjects` |
| Students card | `<StudentList>` + add/enroll/import controls | `GET /classes/:id/students` |
| Grading runs | `<GradingList>` filtered by class (via exam) | `GET /grading-runs?exam_id=…` (multi-step) |
| Exams | `<ExamList>` | `GET /exams` filtered |

---

## 8. `/students`

**Route:** `/students`

| Region | Component | Data |
|---|---|---|
| Header | "Students" + `<Button>Import Excel</Button>` + `<Button>Add student</Button>` | — |
| Table | `<StudentsTable>` (name, student_code, email, classes) | `GET /students` |
| Add-student dialog | `<NewStudentDialog>` | `POST /students` |

---

## 9. `/students/import`

**Route:** `/students/import`
**Purpose:** Excel import wizard

| Step | Component | Data |
|---|---|---|
| 1. Upload | `<FileDropzone>` (accept `.xlsx`) | `POST /students/import/preview` |
| 2. Map columns | `<ColumnMapper>` (drag columns → canonical fields) | preview data + `POST /students/import` |
| 3. Result | `<ImportSummary>` (imported/skipped/errors) | response |

---

## 10. `/exams`

**Route:** `/exams`

| Region | Component | Data |
|---|---|---|
| Header | "Exams" + filters (subject, status, search) + `<Button>New exam</Button>` | — |
| Table | `<ExamsTable>` (title, subject, status badge, questions count, generated date) | `GET /exams` |

---

## 11. `/exams/new` (wizard)

**Route:** `/exams/new`
**Purpose:** multi-step exam creation

| Step | Component | Validation / data |
|---|---|---|
| 1. Subject | subject picker | `GET /subjects` |
| 2. Title + units | title input + units chip input | — |
| 3. Counts & type | `<ExamConfigForm>` (count + mcq/essay/both + counts for "both") | `total_count > 0`; if `both`, sum = total |
| 4. Source (optional) | `<SourceUploader>` (none / image / PDF) | `POST /uploads/presign` + `POST /exams/:id/files` |
| 5. Generate | `<AiJobProgress>` polling `ai_job` | `POST /exams/:id/generate` |
| 6. Review queue | `<QuestionReviewList>` (per question: approve/reject/edit) | `PATCH /questions/:id` + `/approve` |
| 7. Publish | `<PublishConfirmation>` | `POST /exams/:id/publish` → redirect to `/exams/:id` |

---

## 12. `/exams/:id`

| Region | Component | Data |
|---|---|---|
| Header | Title, subject, status badge, `total_count`, generated date | `GET /exams/:id` |
| Tabs | Questions, Files, Source, Activity | — |
| Questions tab | `<QuestionReviewList>` | `GET /exams/:id/questions` |
| Files tab | `<FileAssetTable>` (kind, original_name, rename, download, regenerate) | `GET /exams/:id/files` |
| Source tab | `<SourcePreview>` (image / PDF embed) | `GET /exams/:id/files?kind=source_*` |
| Activity tab | audit log (later) | — |
| Floating CTA | "Start grading run" → `/grading/new?exam_id=:id` | — |

---

## 13. `/exams/:id/files`

**Route:** `/exams/:id/files`
**Purpose:** dedicated file management (also embedded in `/exams/:id` Files tab)

| Region | Component | Data |
|---|---|---|
| Header | "Files" + upload (questions/answers regenerable) | — |
| Table | `<FileAssetTable>` | `GET /exams/:id/files` |
| Rename row | inline edit → `PATCH /exams/:id/files/:fid` | — |
| Download row | `<a href={downloadUrl}>` | `GET /exams/:id/files/:fid/download` |

---

## 14. `/grading`

**Route:** `/grading`

| Region | Component | Data |
|---|---|---|
| Header | "Grading runs" + filter (exam, status) + `<Button>New grading run</Button>` | — |
| Table | `<GradingRunsTable>` (title, exam, status, items graded/total) | `GET /grading-runs` |

---

## 15. `/grading/new`

**Route:** `/grading/new?exam_id=…`
**Purpose:** create a grading run

| Step | Component | Data |
|---|---|---|
| 1. Exam (prefilled from `?exam_id`) | `<ExamPicker>` | `GET /exams` |
| 2. Benchmark | `<BenchmarkChoice>`: use AI-generated key / upload PDF or image | if upload → `POST /uploads/presign` + register |
| 3. Items | `<StudentPicker>` (select students to grade — default = all enrolled in any class) | `GET /students` |
| 4. Run | "Create run" → `POST /grading-runs` → redirect to `/grading/:id` | — |

---

## 16. `/grading/:id`

| Region | Component | Data |
|---|---|---|
| Header | Run title + exam + status badge + Finalize CTA (disabled if flagged items) | `GET /grading-runs/:id` |
| Items table | `<GradingItemsTable>` (student, status, flagged, total_score, max_score_total, upload) | per-item list |
| Upload modal | `<StudentAnswerUpload>` per item | `POST /uploads/presign` + `POST /items` |
| Finalize | `POST /grading-runs/:id/finalize` (gated) | — |
| Results | `<ResultsCsvDownload>` | `GET /grading-runs/:id/results.csv` |

---

## 17. `/grading/:id/items/:itemId`

**Route:** `/grading/:id/items/:itemId`
**Purpose:** per-student review

| Region | Component | Data |
|---|---|---|
| Header | Student name + status badge + flagged summary | `GET /items/:itemId` |
| Left pane | `<AnswerFilePreview>` (image or PDF) | `GET /items/:itemId/files/:fid/download` |
| Right pane | `<ResponsesTable>` (Q#, prompt, ai_score, max_score, confidence, flagged, rationale) | per-question |
| Override row | inline edit teacher_score + rationale | `PATCH /items/:itemId/responses/:rid` |
| Waive-flag | "Approve AI score" button per row | `POST /items/:itemId/waive-flag` (per question) |

---

## 18. Shared components

- `<EmptyState>` — for empty tables / lists.
- `<ErrorBanner>` — top of page for fatal errors.
- `<ConfirmDialog>` — destructive actions (Delete exam, Delete subject, etc.).
- `<AiJobProgress>` — used in `/exams/new` step 5 and as the row indicator in `/grading/:id`.

See [COMPONENT_SPEC.md](./COMPONENT_SPEC.md) for the full component contracts.