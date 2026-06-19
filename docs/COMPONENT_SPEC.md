# Component Specification — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [PAGE_SPEC.md](./PAGE_SPEC.md) · [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) · [API_CONTRACT.md](./API_CONTRACT.md)

The composite components that compose the pages in [PAGE_SPEC.md](./PAGE_SPEC.md). Primitives (Button, Input, Card, etc.) are listed in [DESIGN_SYSTEM.md §2](./DESIGN_SYSTEM.md).

---

## 1. `<ExamWizard>`

Multi-step exam creation wizard used by `/exams/new`.

**Props**
```ts
{
  initial?: Partial<ExamDraft>;
  onComplete: (examId: string) => void;
}
```

**Steps** (matches [PAGE_SPEC.md §11](./PAGE_SPEC.md))
1. Subject picker
2. Title + units
3. Counts & type (`mcq` / `essay` / `both`)
4. Source (none / image / PDF)
5. Generate (renders `<AiJobProgress>`)
6. Review queue (`<QuestionReviewList>`)
7. Publish

**State machine**
```ts
type WizardStep = 'subject' | 'units' | 'config' | 'source' | 'generate' | 'review' | 'publish';
```

**Validation**
- Step 3 (config): `total_count > 0`; if `both`, `mcq_count + essay_count === total_count`.
- Step 4 (source): optional; if `kind=image|pdf`, a registered `file_asset_id` is required before step 5.

---

## 2. `<QuestionReviewList>`

Renders the questions of an exam with approve/edit/reject controls.

**Props**
```ts
{ examId: string; readOnly?: boolean }
```

**Behavior**
- Lists questions ordered by `position`.
- Each row shows: position, prompt, type, options (MCQ) / rubric (essay), `max_score`, `confidence` (if AI), `source_citation` (if any).
- AI-generated questions show a "Generated" badge; manual ones show "Manual".
- Actions per row: **Edit** (opens `<QuestionEditorDialog>`), **Approve** (calls `POST /questions/:qid/approve`), **Reject** (calls `POST /questions/:qid/reject` → status back to `draft`).

---

## 3. `<QuestionEditorDialog>`

**Props**
```ts
{ examId: string; question: Question; onSaved: (q: Question) => void }
```

**Fields**
- `prompt` (textarea)
- `type` (mcq | essay) — locked if question is already approved and `readOnly`
- `max_score` (number, ≥ 0)
- `options.choices[]` (MCQ): each `{ label, is_correct }`; exactly one correct
- `rubric.criteria[]` (essay): each `{ label, points }`
- `source_citation` (read-only display from `ai_meta`)

---

## 4. `<FileAssetTable>`

**Props**
```ts
{
  examId?: string;
  gradingRunId?: string;
  items: FileAsset[];
  onRename: (id: string, newName: string) => void;
  onDelete: (id: string) => void;
  onRegenerate?: (kind: 'questions_pdf' | 'answers_pdf') => void;
}
```

**Columns**
| Kind | Filename | Size | Actions |
|---|---|---|---|
| `questions_pdf` | editable | shown | Rename, Download, Regenerate |
| `answers_pdf` | editable | shown | Rename, Download, Regenerate |
| `source_image` | editable | shown | Rename, Download, View |
| `source_pdf` | editable | shown | Rename, Download, View |
| `benchmark_*` | editable | shown | Rename, Download |
| `student_answer` | editable | shown | Rename, Download, View |

**Rename UX**
- Click filename → input → blur saves (or Esc cancels).

---

## 5. `<ColumnMapper>` (Excel drag-to-map)

**Props**
```ts
{
  preview: ImportPreview;
  onSubmit: (mapping: FieldMapping) => void;
}
```

**Visual**
```
┌─────────────────────────────┐  ┌──────────────────────┐
│  Spreadsheet columns         │  │  Canonical fields    │
│  (read-only, sample rows)   │  │  (drop targets)      │
│                              │  │                      │
│  ▢ A — Student Name          │  │  ◯ name        ← A   │
│  ▢ B — Student ID            │  │  ◯ student_id  ← B   │
│  ▢ C — Email                 │  │  ◯ email       ← C   │
│  ▢ D — Homeroom              │  │  ◯ extra:homeroom   │
│                              │  │                      │
└─────────────────────────────┘  └──────────────────────┘
       (HTML5 drag-and-drop)
```

**Rules**
- `name` mapping is required; submit disabled until filled.
- Unmapped columns become `extra:<original_header>` if the user drags them into the "extras" zone; otherwise they are dropped.

---

## 6. `<AiJobProgress>`

**Props**
```ts
{ jobId: string | null; onComplete?: (job: AiJob) => void; onFailed?: (job: AiJob) => void }
```

**Visual**
```
┌─────────────────────────────────────────┐
│  ⏳ Generating questions…               │
│  [indeterminate progress]               │
│  job_status: processing                  │
│  estimated 10–30 seconds                │
└─────────────────────────────────────────┘
```

**Internals**
- Uses `useAiJob(jobId)` from `hooks/useAiJob.ts`.
- On `done` → `onComplete(job)`.
- On `failed` → show error + `Retry` button.

---

## 7. `<GradingItemsTable>`

**Props**
```ts
{ runId: string; items: GradingItem[]; onUpload: (itemId: string) => void }
```

**Columns**
| Student | Status | Flagged | Total | Max | Uploaded file | Actions |
|---|---|---|---|---|---|---|
| name + student_code | badge | ⚠ if flagged | numeric / "—" | numeric | link to view | Upload, Review |

**Status mapping**
- `pending` → "Waiting for upload"
- `ai_processing` → "AI grading…"
- `ai_done` → "Graded" + click → `/grading/:id/items/:itemId`
- `reviewed` → "Reviewed" + click
- `final` → "Final" (read-only)

**Flag indicator**
- Orange left border if `flagged && !finalized`.
- Hover tooltip: "Needs review before finalize".

---

## 8. `<ResponsesTable>` (per-student grading review)

**Props**
```ts
{ itemId: string; responses: GradingResponse[]; onOverride: (rid: string, score: number, rationale?: string) => void; onWaiveFlag: (rid: string) => void }
```

**Columns**
| Q# | Prompt | AI score | Max | Confidence | Flagged | Rationale | Teacher score | Actions |
|---|---|---|---|---|---|---|---|---|
| 1 | prompt text | number | number | 0.92 | ⚠ | "extracted text matched" | editable | Save / Waive |

**Override UX**
- Click `Teacher score` → input → Enter saves.
- If `flagged`, the "Waive" button confirms "Approve AI score without change".

---

## 9. `<BenchmarkChoice>`

**Props**
```ts
{ examId: string; value: BenchmarkChoiceValue | null; onChange: (v: BenchmarkChoiceValue) => void }
```

**Value shape**
```ts
type BenchmarkChoiceValue =
  | { kind: 'exam_answer_key' }
  | { kind: 'uploaded'; fileAssetId: string };
```

**Visual**
- Two radio cards:
  - **Use AI-generated answer key** (default; preview button opens a modal showing the answer key JSON).
  - **Upload a benchmark** (PDF or image) → opens `<FileUploader>` → registers a `file_asset`.

---

## 10. `<StudentAnswerUpload>`

**Props**
```ts
{ gradingRunId: string; itemId: string; onUploaded: (jobId: string) => void }
```

**Flow**
1. User picks a file (`.pdf`, `.jpg`, `.png`).
2. `POST /uploads/presign` → PUT to MinIO.
3. `POST /grading-runs/:id/items { student_id, file_asset_id }` → returns `ai_job`.
4. `<AiJobProgress>` polls the job.

---

## 11. `<FinalizeGuard>`

**Props**
```ts
{ runId: string; hasUnreviewedFlags: boolean; onFinalize: () => void }
```

**Behavior**
- Renders a `<Button>` disabled with tooltip "Review X flagged items first" if `hasUnreviewedFlags`.
- On click → `POST /grading-runs/:id/finalize` with `Idempotency-Key`.

---

## 12. `<EmptyState>` (shared)

**Props**
```ts
{ title: string; description?: string; action?: { label: string; onClick: () => void } }
```

Used wherever a list is empty (no subjects, no exams, no students, etc.).

---

## 13. `<ConfirmDialog>` (shared)

**Props**
```ts
{ open: boolean; title: string; description: string; confirmLabel?: string; destructive?: boolean; onConfirm: () => void; onCancel: () => void }
```

Used for delete actions.

---

## 14. Open items

- **`<QuestionEditorDialog>` locking:** should editing an approved question revert it to `in_review`? Decision: yes (re-review required).
- **Real-time updates:** use SSE or WebSocket for AI job completion to avoid polling? Default to polling for simplicity.