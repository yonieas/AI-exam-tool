# Teacher AI Exam Tool

A focused single-teacher web app whose signature feature is an **AI exam subsystem**:
generate questions + answer keys from a subject/units or an uploaded image/PDF
source, and grade typed/handwritten/PDF student submissions against an AI-generated
or uploaded benchmark answer key.

The product, architecture, schema, API contract, AI subsystem, frontend, and
build sequence are fully specified in `docs/`. This README is a quick start.

## Quick start (dev)

```bash
# 1. Bring up the infra
docker compose up -d postgres redis minio

# 2. Backend
cd api
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# In another shell, seed demo data:
python -m app.scripts.seed

# 3. Frontend
cd ../web
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
# Open http://localhost:3000
```

## Layout

```
.
├── api/                  # FastAPI modular monolith + AI worker
│   ├── app/
│   │   ├── modules/      # auth, subjects, classes, students, exams, questions, grading, files, uploads, ai_jobs, me
│   │   ├── ai/           # AIProvider port + mock + MiniMax adapter + prompts
│   │   ├── workers/      # in-process AI job worker (asyncio queue)
│   │   ├── models/       # SQLAlchemy ORM
│   │   └── main.py
│   ├── tests/            # pytest integration + owner-isolation
│   ├── Dockerfile
│   └── requirements.txt
├── web/                  # Next.js 14 + React 18 + TS + Tailwind
│   ├── app/              # App Router pages
│   ├── components/
│   └── lib/
├── docs/                 # Source of truth (PRD, ARCHITECTURE, ERD, API_CONTRACT, etc.)
├── docker-compose.yml    # postgres + redis + minio + api + ai-worker + web
└── README.md
```

## Testing

```bash
# Backend integration + owner-isolation tests
cd api && python3 -m pytest tests/integration/ -v
```

The smoke test covers: dev-login → subjects/classes/students CRUD →
enrollments → exam creation → AI question generation → question
approval → exam publication → grading run creation → per-student answer
upload → AI grading → flagged-item waiver → finalization → CSV export
→ cross-owner isolation.

## Dev sign-in

When `DEV_LOGIN_ENABLED=true` (default in `.env.example`), the backend
exposes `POST /api/v1/auth/dev-login` which mints a real access JWT
and sets a rotating refresh cookie. This is the shortest path to
exercising the full app without configuring Google OAuth.

## AI provider

The active provider is selected by `AI_PROVIDER` env (default `minimax`).
The MiniMax adapter calls MiniMax's OpenAI-compatible endpoint
(`MINIMAX_BASE_URL`, default `https://api.minimax.io/v1`, model
`MINIMAX_MODEL`, default `MiniMax-M2.7`). For local dev without a key,
set `AI_PROVIDER=mock` — a deterministic mock returns structured
QuestionSet / GradingResult payloads so the full flow can be exercised
end-to-end.
