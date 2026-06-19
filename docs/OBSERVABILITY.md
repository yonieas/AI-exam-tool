# Observability — Teacher AI Exam Tool

> **Product:** Teacher AI Exam Tool
> **Status:** Implementation-ready v1.0
> **Last updated:** 2026-06-18
> **Derives from:** [ARCHITECTURE.md §12](./ARCHITECTURE.md) · [BACKEND_CONVENTIONS.md §12](./BACKEND_CONVENTIONS.md)

Observability for the single-service FastAPI monolith + Next.js app. Single-teacher scope means simplified tracing, no per-school dashboards, and no FERPA/COPPA compliance layers.

---

## 1. Goals

| # | Goal |
|---|---|
| O1 | Every request is traceable from browser → API → DB / MinIO |
| O2 | No student PII or answer content in any log, metric, or trace |
| O3 | AI quality is measurable (confidence, flagged rate, teacher override rate) |
| O4 | Incidents are paged by severity, not volume |
| O5 | SLOs are tracked and alertable |

---

## 2. Instrumentation

### 2.1 Traces

- **OpenTelemetry (OTel) auto-instrumentation** in FastAPI (HTTP), SQLAlchemy (SQL), `httpx` (MinIO calls), and the BullMQ worker.
- **Trace propagation:** W3C `traceparent` header from browser → API → worker (via Redis job metadata).
- **No PII in trace attributes** — only UUIDs (`exam_id`, `owner_id`, `job_id`) and operation names.

### 2.2 Metrics

Prometheus exporter on `GET /metrics`.

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `path`, `status_code` | Request volume |
| `http_request_duration_seconds` | Histogram | `method`, `path` | p95/p99 latency |
| `ai_job_total` | Counter | `job_type`, `job_status`, `ai_provider`, `model` | AI job count |
| `ai_job_tokens_input_total` | Counter | `job_type`, `ai_provider`, `model` | Total tokens in |
| `ai_job_tokens_output_total` | Counter | `job_type`, `ai_provider`, `model` | Total tokens out |
| `ai_job_cost_usd_micro_total` | Counter | `job_type`, `ai_provider`, `model` | Total cost |
| `ai_job_flagged_rate` | Gauge | `job_type` | Fraction of items flagged |
| `ai_job_teacher_override_rate` | Gauge | `job_type` | Fraction of responses overridden |
| `grading_finalize_duration_seconds` | Histogram | — | Time from run creation to finalize |
| `minio_upload_bytes_total` | Counter | `kind` | Bytes uploaded to MinIO |

### 2.3 Logs

Structured JSON to stdout (captured by the Docker logging driver).

Every log line carries:
```
trace_id   uuid    W3C traceparent from the request
owner_id   uuid    current user's id (not their name)
service    string  "api" | "ai-worker"
```

**Rule O2: never log** `student.name`, `student.email`, `submission.answer_text`, `question.prompt`, or `response.ai_rationale`. Use IDs only.

---

## 3. SLOs

| SLO | Target | SLI |
|---|---|---|
| **API availability** | 99.9% / month | `http_requests_total{status!~"5.."} / http_requests_total` |
| **API latency (p95)** | < 400 ms (non-AI) | `http_request_duration_seconds{p95}` |
| **AI generation (p95)** | < 30 s | `ai_generation_duration_seconds{p95}` |
| **AI grading (p95)** | < 20 s / submission | `ai_grading_duration_seconds{p95}` |
| **AI job success rate** | ≥ 99% | `ai_job_total{job_status="done"} / ai_job_total` |
| **AI human-override rate** | ≤ 15% | `ai_job_teacher_override_rate` |

### 3.1 Error budget

- Monthly error budget = (1 − SLO target) × 43,200 min.
- Burn rate alerting: if 10% of budget burns in 1 h → warning page; 1% in 10 min → SEV2 page.

---

## 4. Alerting

| Severity | Trigger | Action |
|---|---|---|
| **SEV1** | `ai_job_total{job_status="failed"}` > 5% in 5 min | Page; check MiniMax status + provider keys |
| **SEV2** | `http_requests_total{status=~"5.."}` > 1% in 5 min | Slack alert |
| **SEV2** | `ai_job_teacher_override_rate` > 20% for 1 h | Slack; review confidence threshold |
| **WARN** | `ai_job_cost_usd_micro_total` on track to exceed monthly budget | Email |

---

## 5. Dashboards

Single Grafana instance per environment.

**Panels:**
1. **API Overview** — request rate, error rate, p95 latency
2. **AI Health** — job success rate, flagged rate, override rate, cost
3. **Database** — connection pool, query latency, replication lag
4. **Queue** — BullMQ depth (`ai:generation`, `ai:grading`), processing time
5. **SLO burn** — error budget remaining per SLO

No per-student or per-exam drilldown at MVP (P2 if needed).

---

## 6. PII handling

Per [ARCHITECTURE.md §1 P6](./ARCHITECTURE.md), student data (names, emails, answer content) is **never written to logs, metrics, or traces**. Accepted at implementation: `owner_id` (UUID), `exam_id`, `student_id` (UUID), counts.

---

## 7. Open items

- **OTel collector:** sidecar or agent per container? Recommend an OTel collector sidecar for the API and worker; the web is instrumented by the Next.js tracing SDK.
- **Distributed tracing across BullMQ:** propagate `traceparent` in the job payload so the worker's spans are linked to the original request's trace.