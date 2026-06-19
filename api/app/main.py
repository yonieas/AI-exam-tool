"""FastAPI app entrypoint."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import Base, engine, SessionLocal
from app.errors import install_error_handlers
from app.storage.minio_client import get_minio
from app.workers.ai_worker import get_worker

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    # Ensure MinIO bucket exists
    try:
        await get_minio().ensure_bucket()
    except Exception as e:
        logger.warning("MinIO not reachable at startup: %s", e)

    # Worker
    worker = get_worker()
    worker.set_session_factory(SessionLocal)
    await worker.start()
    app.state.worker = worker

    # Create tables if not yet (development convenience)
    try:
        async with engine.begin() as conn:
            # Create required PG extensions
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
            except Exception as e:
                logger.warning("Could not create extensions (need superuser): %s", e)

        # Create ENUM types in a separate transaction
        enums = [
            ("question_type_mode", "('mcq','essay','both')"),
            ("exam_source_kind", "('none','image','pdf')"),
            ("exam_status", "('draft','in_review','published','closed')"),
            ("question_type", "('mcq','essay')"),
            ("question_status", "('draft','in_review','approved')"),
            ("benchmark_kind", "('exam_answer_key','uploaded')"),
            ("grading_run_status", "('draft','grading','needs_review','finalized')"),
            ("grading_item_status", "('pending','ai_processing','ai_done','reviewed','final')"),
            ("file_asset_kind", "('source_image','source_pdf','questions_pdf','answers_pdf','benchmark_pdf','benchmark_image','student_answer')"),
            ("ai_job_type", "('question_generation','grading')"),
            ("ai_job_status", "('queued','processing','done','failed')"),
            ("ai_provider", "('minimax','mock')"),
        ]
        for type_name, values in enums:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(f"CREATE TYPE {type_name} AS ENUM {values}"))
            except Exception as e:
                if "already exists" not in str(e):
                    logger.debug("Enum %s create: %s", type_name, e)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error("DB init error: %s", e)

    yield
    await worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Teacher AI Exam Tool", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        t0 = time.time()
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    install_error_handlers(app)

    @app.get("/api/v1/livez", tags=["health"])
    async def livez() -> dict:
        return {"status": "ok"}

    @app.get("/api/v1/readyz", tags=["health"])
    async def readyz() -> dict:
        checks = {}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"
        try:
            mn = get_minio()
            checks["minio"] = "ok" if mn._client.bucket_exists(mn.bucket) else "missing_bucket"
        except Exception as e:
            checks["minio"] = f"error: {e}"
        try:
            w = get_worker()
            r = w._get_redis()
            if r is not None:
                await r.ping()
                checks["redis"] = "ok"
            else:
                checks["redis"] = "unavailable (dev)"
        except Exception as e:
            checks["redis"] = f"error: {e}"
        overall = all(v == "ok" for v in checks.values() if v != "unavailable (dev)")
        return {"status": "ok" if overall else "degraded", "checks": checks}

    # Routers
    from app.modules.auth.routes import router as auth_router
    from app.modules.me.routes import router as me_router
    from app.modules.subjects.routes import router as subjects_router
    from app.modules.classes.routes import router as classes_router
    from app.modules.students.routes import router as students_router
    from app.modules.exams.routes import router as exams_router
    from app.modules.questions.routes import router as questions_router
    from app.modules.files.routes import exam_router as files_exam_router, run_router as files_run_router
    from app.modules.uploads.routes import router as uploads_router
    from app.modules.grading.routes import router as grading_router
    from app.modules.ai_jobs.routes import router as ai_jobs_router

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(subjects_router, prefix="/api/v1")
    app.include_router(classes_router, prefix="/api/v1")
    app.include_router(students_router, prefix="/api/v1")
    app.include_router(exams_router, prefix="/api/v1")
    app.include_router(questions_router, prefix="/api/v1")
    app.include_router(files_exam_router, prefix="/api/v1")
    app.include_router(files_run_router, prefix="/api/v1")
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(grading_router, prefix="/api/v1")
    app.include_router(ai_jobs_router, prefix="/api/v1")

    return app


app = create_app()
