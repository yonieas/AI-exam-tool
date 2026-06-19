# Design System — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [PRD.md](./PRD.md) · [FRONTEND_ARCHITECTURE.md](./FRONTEND_ARCHITECTURE.md)
> **Consumed by:** [PAGE_SPEC.md](./PAGE_SPEC.md) · [COMPONENT_SPEC.md](./COMPONENT_SPEC.md)

Tokens, primitives, and conventions for the single teacher portal. **No per-school theming** — one theme.

---

## 1. Tokens

CSS variables in `app.css` (Tailwind v4 theme layer). Single light mode at MVP; dark mode is P2.

### 1.1 Color

```
--color-bg           #FAFAFA
--color-surface      #FFFFFF
--color-surface-2    #F4F4F5
--color-border       #E4E4E7
--color-text         #18181B
--color-text-muted   #71717A

--color-primary      #2563EB      /* actions, links */
--color-primary-fg   #FFFFFF
--color-success      #16A34A
--color-warning      #D97706
--color-danger       #DC2626
--color-info         #0891B2
```

**Status semantics (used everywhere):**

| Status | Token | Examples |
|---|---|---|
| success | `--color-success` | "Approved", "Finalized", "Uploaded" |
| warning | `--color-warning` | "Pending review", "AI in progress" |
| danger | `--color-danger` | "Flagged", "Failed", "Conflict" |
| info | `--color-info` | "AI generated", "Polling" |

### 1.2 Spacing

4-px scale: `0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64` (Tailwind default).

### 1.3 Typography

- Font: Inter (system fallback).
- Scale: `text-xs 12`, `text-sm 14`, `text-base 16`, `text-lg 18`, `text-xl 20`, `text-2xl 24`, `text-3xl 30`.
- Headings: `font-semibold`; body: `font-normal`.

### 1.4 Radius

`rounded-md 6`, `rounded-lg 8`, `rounded-xl 12`. Default for cards: `rounded-lg`.

### 1.5 Shadow

`shadow-sm`, `shadow`, `shadow-md` (default for cards & modals).

---

## 2. Primitives (Radix-based)

| Component | Notes |
|---|---|
| `Button` | `variant: primary | secondary | ghost | danger`, `size: sm | md | lg` |
| `Input` | text + number + file |
| `Textarea` | autosize |
| `Select` | Radix `Select` |
| `Dialog` | Radix `Dialog` |
| `Sheet` | Radix `Dialog` (side=Right) for the file drawer |
| `Tabs` | Radix `Tabs` |
| `Tooltip` | Radix `Tooltip` |
| `Toast` | Radix `Toast` |
| `Dropdown` | Radix `DropdownMenu` |
| `Table` | TanStack Table styling (see below) |
| `Card` | `rounded-lg shadow-sm` over `--color-surface` |
| `Badge` | `variant: success | warning | danger | info | neutral` |
| `Progress` | indeterminate (AI running) + determinate (upload) |
| `Spinner` | small loader |

### 2.1 Table styling

```
header row:  text-xs text-muted uppercase tracking-wide
data row:    hover:bg-surface-2
cell:        px-4 py-3 text-sm
```

---

## 3. Async / AI states

| State | Visual |
|---|---|
| **Idle** | no badge |
| **Queued** | `<Badge variant="info">Queued</Badge>` + `<Spinner size="sm" />` |
| **Processing** | `<Progress indeterminate />` + label "Generating questions…" / "Grading…" |
| **Done** | `<Badge variant="success">Done</Badge>` + result |
| **Failed** | `<Badge variant="danger">Failed</Badge>` + retry button |
| **Flagged (per question)** | `<Badge variant="warning">Low confidence</Badge>` |
| **Flagged (per item)** | orange left border on the row + tooltip "Needs review" |

---

## 4. Layout

- **Top bar** (h-14): app name, user avatar (dropdown: Sign out).
- **Sidebar** (w-56): Dashboard, Subjects, Classes, Students, Exams, Grading.
- **Main area:** max-w-6xl, mx-auto, p-6.

```
┌─────────────────────────────────────────────┐
│  Top bar                                    │
├──────┬──────────────────────────────────────┤
│      │                                      │
│ Side │  Main content                        │
│ bar  │                                      │
│      │                                      │
└──────┴──────────────────────────────────────┘
```

---

## 5. Form conventions

- Labels above inputs (`mb-1`).
- Required indicator: red `*` after the label.
- Help text: `text-xs text-muted` below the input.
- Validation: red border + `text-xs text-danger` message.
- Save buttons: right-aligned, primary.

---

## 6. A11y

- All interactive elements keyboard-reachable (Tab order matches visual order).
- Focus ring: 2px `--color-primary` outline with offset.
- `aria-label` on icon-only buttons.
- Modals trap focus and restore on close.
- Color contrast ≥ 4.5:1 on text.
- Form errors announced via `aria-describedby`.

---

## 7. Motion

- Default transition: `transition-colors duration-150`.
- Modal/dialog enter: `data-[state=open]:animate-in fade-in-0 zoom-in-95`.
- Polling spinners: `animate-spin`.

---

## 8. Open items

- **Dark mode:** P2.
- **Brand colors:** placeholder (`--color-primary = #2563EB`). Replace with brand at deploy time.