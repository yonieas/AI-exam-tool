# Deployment — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [ARCHITECTURE.md](./ARCHITECTURE.md) · [BACKEND_CONVENTIONS.md](./BACKEND_CONVENTIONS.md)

Dockerized FastAPI monolith + Next.js + PostgreSQL + MinIO + Redis. One `docker-compose.yml` per environment.

---

## 1. Topology

```mermaid
flowchart TB
  subgraph App
    web[Next.js]
    api[FastAPI]
    worker[AI Worker]
  end
  subgraph Data
    pg[(Postgres 16)]
    minio[(MinIO)]
    redis[(Redis 7)]
  end

  web -- REST --> api
  api -- SQL --> pg
  api -- S3 API --> minio
  api -- enqueue --> redis
  worker -- consume --> redis
  worker -- OpenAI SDK --> claude((MiniMax))
  api -- presigned URLs --> minio
```

- **`api`** — FastAPI monolith; HTTP only.
- **`web`** — Next.js; SSR/RSC + client bundle.
- **`worker`** — separate process (same image as `api`, different command) consuming BullMQ; calls the in-process AI adapter.
- **`postgres`** — primary DB; WAL archiving on host for PITR.
- **`minio`** — single-node at MVP; multi-node replicated for prod.
- **`redis`** — sessions + BullMQ broker.

---

## 2. `docker-compose.yml` (dev / staging / prod)

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: examtool
      POSTGRES_USER: examtool
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "examtool"]
      interval: 5s

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redisdata:/data
    ports: ["6379:6379"]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - miniodata:/data
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # console
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s

  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_started }
      minio:    { condition: service_healthy }
    ports: ["8000:8000"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/readyz"]
      interval: 10s

  ai-worker:
    build:
      context: ./api
      dockerfile: Dockerfile
    command: ["python", "-m", "app.workers.ai_worker"]
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_started }
      minio:    { condition: service_healthy }

  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    environment:
      NEXT_PUBLIC_API_BASE_URL: ${API_BASE_URL}
    ports: ["3000:3000"]
    depends_on:
      api: { condition: service_healthy }

volumes:
  pgdata: {}
  redisdata: {}
  miniodata: {}
```

> **Prod note:** swap `minio` for a multi-node MinIO setup, set `miniodata` to a network volume, and put CloudFront / nginx in front for TLS termination.

---

## 3. Environment variables (`.env`)

```bash
# General
APP_ENV=dev
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://examtool:${POSTGRES_PASSWORD}@postgres:5432/examtool

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=${MINIO_ROOT_USER}
MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD}
MINIO_BUCKET=examtool
MINIO_PUBLIC_BASE_URL=http://localhost:9000    # used in presigned URL host

# Auth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
JWT_SIGNING_KEY=...                       # vault-managed in prod
JWT_ACCESS_TTL_SECONDS=900                # 15 min
JWT_REFRESH_TTL_SECONDS=2592000           # 30 d
COOKIE_DOMAIN=localhost
COOKIE_SECURE=false                       # true in prod

# AI provider (ADR-009)
AI_PROVIDER=minimax
MINIMAX_API_KEY=...
# OpenAI-compatible endpoint for MiniMax (override only if MiniMax moves the host)
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-M2.7
# Cheap tier — currently the same model as premium; override when MiniMax ships a fast variant
MINIMAX_CHEAP_MODEL=MiniMax-M2.7

# Frontend
API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

> **No `school_id`, no Stripe, no payment-gateway keys.** The runtime DB role is `examtool_app` with **no `BYPASSRLS`** (multi-tenancy is application-layer `owner_id` filtering).

---

## 4. Probes

| Path | Purpose | Returns |
|---|---|---|
| `GET /api/v1/livez` | liveness — process is running | `200 OK` |
| `GET /api/v1/readyz` | readiness — DB + Redis + MinIO reachable | `200 OK` or `503` with reason |

---

## 5. Backup & restore

- **Postgres:** nightly base backup + WAL archiving (`wal-g` or `pg_basebackup` + S3); RPO ≤ 5 min, RTO ≤ 1 h (per [PRD §6](./PRD.md)).
- **MinIO:** `mc mirror` between buckets nightly; document restore runbook.
- **Redis:** ephemeral — BullMQ jobs are recoverable from `ai_job.status='queued'` rows on startup.

---

## 6. Production hardening checklist

- [ ] TLS termination at the edge (nginx / CloudFront).
- [ ] All secrets in a vault (AWS Secrets Manager / HashiCorp Vault).
- [ ] `COOKIE_SECURE=true`; `COOKIE_DOMAIN` set to the apex.
- [ ] Postgres backups encrypted + cross-region replicated.
- [ ] MinIO erasure-coded (4 drives minimum for prod).
- [ ] Logging redaction confirmed (no PII / no answer content) per [OBSERVABILITY.md](./OBSERVABILITY.md).
- [ ] Rate limiting on `/auth/*` (Redis token bucket per IP).
- [ ] AI provider key rotation procedure documented.

---

## 7. Local dev quickstart

```bash
# 1. Clone
git clone <repo> && cd lms

# 2. Copy env template
cp .env.example .env
# Fill in GOOGLE_CLIENT_ID/SECRET, MINIMAX_API_KEY

# 3. Bring up the stack
docker compose up -d postgres redis minio
docker compose run --rm api alembic upgrade head
docker compose up -d api ai-worker web

# 4. Open
open http://localhost:3000
```

---

## 8. Open items

- **AI key isolation:** in production, ensure the `ai-worker` is the only container with `MINIMAX_API_KEY`; `api` carries it too at MVP (it dispatches synchronously for short tasks). Restrict via env scoping in prod.
- **MinIO TLS:** enable TLS at the MinIO listener in prod; presigned URLs must use the public hostname.