"""End-to-end smoke test of the API: dev-login → CRUD all entities → AI generation → grading → CSV."""
from __future__ import annotations

import io
import os
import time

import pytest
from fastapi.testclient import TestClient

# Set env before importing the app
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://examtool:examtool@localhost:5432/examtool")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEV_LOGIN_ENABLED", "true")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ["EXAMTOOL_WORKER_DISABLED"] = "1"

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    # TestClient creates a new event loop per fixture; the engine pool holds
    # connections bound to the previous loop, so dispose it before each test.
    from app.db import engine
    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(engine.dispose())
    except Exception:
        pass
    with TestClient(app) as c:
        yield c
    try:
        asyncio.get_event_loop().run_until_complete(engine.dispose())
    except Exception:
        pass


def _login(client) -> str:
    r = client.post("/api/v1/auth/dev-login", json={"email": f"smoke-{int(time.time()*1000)}@example.com", "full_name": "Smoke User"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_livez(client):
    r = client.get("/api/v1/livez")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_happy_path(client):
    token = _login(client)
    h = _hdrs(token)

    # Create subject
    r = client.post("/api/v1/subjects", headers=h, json={"name": "Physics", "code": "PHYS"})
    assert r.status_code == 201, r.text
    subject = r.json()

    # Create class with subject
    r = client.post("/api/v1/classes", headers=h, json={"name": "Grade 10-A", "grade_level": 10, "subject_ids": [subject["id"]]})
    assert r.status_code == 201, r.text
    klass = r.json()
    assert klass["subject_ids"] == [subject["id"]]
    assert klass["student_count"] == 0

    # Create students
    student_ids = []
    for i in range(3):
        r = client.post("/api/v1/students", headers=h, json={"name": f"Student {i}", "student_code": f"S{i:03d}"})
        assert r.status_code == 201, r.text
        student_ids.append(r.json()["id"])
    # Enroll all
    for sid in student_ids:
        r = client.post(f"/api/v1/classes/{klass['id']}/enrollments", headers=h, json={"student_id": sid})
        assert r.status_code == 201, r.text

    # List class students
    r = client.get(f"/api/v1/classes/{klass['id']}/students", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 3

    # Create exam
    r = client.post("/api/v1/exams", headers=h, json={
        "subject_id": subject["id"],
        "title": "Physics Unit 1",
        "units": ["Kinematics", "Forces"],
        "question_type_mode": "both",
        "total_count": 4,
        "mcq_count": 2,
        "essay_count": 2,
        "generation_config": {"language": "en", "difficulty": "medium"},
    })
    assert r.status_code == 201, r.text
    exam = r.json()
    assert exam["status"] == "draft"
    assert exam["question_count"] == 0

    # Trigger generation
    r = client.post(f"/api/v1/exams/{exam['id']}/generate", headers=h, params={"Idempotency-Key": "test-idem-1"})
    assert r.status_code == 202, r.text
    job = r.json()["ai_job"]
    # In test mode the job runs inline; in production it would be queued and polled here.
    assert job["job_status"] in ("queued", "done")

    # Wait for AI job to complete (mock is fast)
    for _ in range(40):
        time.sleep(0.25)
        r = client.get(f"/api/v1/ai-jobs/{job['id']}", headers=h)
        if r.status_code == 200 and r.json()["job_status"] in ("done", "failed"):
            break
    assert r.json()["job_status"] == "done", r.text

    # List questions
    r = client.get(f"/api/v1/exams/{exam['id']}/questions", headers=h)
    assert r.status_code == 200, r.text
    questions = r.json()["data"]
    if len(questions) != 4:
        # Debug: re-fetch the job
        jr = client.get(f"/api/v1/ai-jobs/{job['id']}", headers=h)
        print("JOB STATE:", jr.json())
    assert len(questions) == 4
    # All in_review
    for q in questions:
        assert q["status"] == "in_review"

    # Approve all
    for q in questions:
        r = client.post(f"/api/v1/exams/{exam['id']}/questions/{q['id']}/approve", headers=h)
        assert r.status_code == 200, r.text

    # Publish
    r = client.post(f"/api/v1/exams/{exam['id']}/publish", headers=h)
    assert r.status_code == 200, r.text
    pub = r.json()
    assert pub["status"] == "published"
    assert pub["questions_pdf_file_id"] is not None

    # Download PDFs
    r = client.get(f"/api/v1/exams/{exam['id']}/pdf/questions", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 100
    r = client.get(f"/api/v1/exams/{exam['id']}/pdf/answers", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"

    # Create grading run
    r = client.post("/api/v1/grading-runs", headers=h, json={
        "exam_id": exam["id"], "title": "Period 3 grading", "benchmark_kind": "exam_answer_key", "student_ids": student_ids,
    })
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "draft"

    # Upload a tiny image (1x1 PNG) for each student
    png_bytes = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108020000009077533de0000000017352474200aece1ce90000000d49444154789c63f8cf00000003000100182dd5b40000000049454e44ae426082")
    for sid in student_ids:
        # Presign
        r = client.post("/api/v1/uploads/presign", headers=h, json={"kind": "student_answer", "grading_run_id": run["id"], "filename": "ans.png", "mime_type": "image/png", "size_bytes": len(png_bytes)})
        assert r.status_code == 201, r.text
        presign = r.json()
        # In test mode, write directly to MinIO via the SDK (bypassing the public presign host)
        from app.storage.minio_client import get_minio
        import asyncio
        asyncio.get_event_loop().run_until_complete(get_minio().put_bytes(presign["storage_key"], png_bytes, "image/png"))
        # Register file_asset
        r = client.post(f"/api/v1/grading-runs/{run['id']}/files", headers=h, json={"kind": "student_answer", "storage_key": presign["storage_key"], "original_name": "ans.png", "mime_type": "image/png", "size_bytes": len(png_bytes)})
        assert r.status_code == 201, r.text
        fa = r.json()
        # Register grading item
        r = client.post(f"/api/v1/grading-runs/{run['id']}/items", headers=h, json={"student_id": sid, "file_asset_id": fa["id"]}, params={"Idempotency-Key": f"grade-{sid}"})
        assert r.status_code == 202, r.text

    # Wait for all grading jobs
    r = client.get(f"/api/v1/grading-runs/{run['id']}", headers=h)
    run = r.json()
    assert run["item_count"] == 3

    # Poll until all items have status=ai_done
    for _ in range(60):
        r = client.get(f"/api/v1/grading-runs/{run['id']}/items", headers=h)
        items = r.json()["data"]
        if all(i["status"] in ("ai_done", "reviewed", "final") for i in items):
            break
        time.sleep(0.5)
    items = r.json()["data"]
    for it in items:
        assert it["status"] in ("ai_done", "reviewed", "final"), it
        assert float(it["max_score_total"]) > 0, it

    # Finalize: if any item is flagged, override or waive first
    flagged = [i for i in items if i["flagged"]]
    for it in flagged:
        r = client.post(f"/api/v1/grading-runs/{run['id']}/items/{it['id']}/waive-flag", headers=h)
        assert r.status_code == 200, r.text

    r = client.post(f"/api/v1/grading-runs/{run['id']}/finalize", headers=h)
    assert r.status_code == 200, r.text
    final = r.json()
    assert final["status"] == "finalized"

    # CSV export
    r = client.get(f"/api/v1/grading-runs/{run['id']}/results.csv", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "student_id,student_name" in r.text


def test_owner_isolation(client):
    # Two users; user A should not see user B's data
    a = _login(client)
    b = _login(client)
    h_a = _hdrs(a)
    h_b = _hdrs(b)

    r = client.post("/api/v1/subjects", headers=h_a, json={"name": "A-subject"})
    assert r.status_code == 201
    a_subj_id = r.json()["id"]

    # B lists subjects — must NOT include A's
    r = client.get("/api/v1/subjects", headers=h_b)
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["data"]]
    assert a_subj_id not in ids

    # B tries to read A's subject — 404
    r = client.get(f"/api/v1/subjects/{a_subj_id}", headers=h_b)
    assert r.status_code == 404


def test_excel_import(client):
    from openpyxl import Workbook
    token = _login(client)
    h = _hdrs(token)

    # Build a sample .xlsx
    wb = Workbook()
    ws = wb.active
    ws.append(["Student Name", "Student ID", "Email", "Homeroom"])
    for i in range(5):
        ws.append([f"Imported Student {i}", f"S{i:03d}", f"u{i}@example.com", "10A"])
    import io
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # Preview
    r = client.post("/api/v1/students/import/preview", headers=h, files={"file": ("students.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["row_count"] == 5
    assert any(c["header"] == "Student Name" for c in preview["columns"])

    # Import
    buf.seek(0)
    import json
    mapping = json.dumps({"name": "A", "student_code": "B", "email": "C", "extra_columns": {"homeroom": "D"}})
    r = client.post(
        "/api/v1/students/import",
        headers=h,
        files={"file": ("students.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"mapping": mapping, "rows": "process_all"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 5
    assert body["skipped"] == 0

    # Verify the students are visible
    r = client.get("/api/v1/students", headers=h)
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["data"]]
    assert "Imported Student 0" in names
    # extra_columns persisted
    found = next((s for s in r.json()["data"] if s["name"] == "Imported Student 0"), None)
    assert found is not None
    assert found["extra_columns"].get("homeroom") == "10A"
