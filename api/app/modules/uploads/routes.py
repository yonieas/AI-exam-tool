"""Upload presign route."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, NotFoundError
from app.models.exam import Exam
from app.models.grading import GradingRun
from app.modules.uploads.schemas import PresignRequest, PresignResponse
from app.storage.minio_client import get_minio

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Map file_asset_kind → top-level storage prefix
_PREFIXES = {
    "source_image": "sources",
    "source_pdf": "sources",
    "benchmark_pdf": "benchmarks",
    "benchmark_image": "benchmarks",
    "student_answer": "grading",
    "questions_pdf": "exams",
    "answers_pdf": "exams",
}


@router.post("/presign", response_model=PresignResponse, status_code=201)
async def presign(
    body: PresignRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresignResponse:
    if body.kind not in _PREFIXES:
        raise BadRequestError(f"Invalid kind: {body.kind}")
    # Validate parent ownership
    if body.exam_id:
        e = (await db.execute(select(Exam).where(Exam.id == body.exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
        if not e:
            raise NotFoundError("Exam not found.")
    if body.grading_run_id:
        r = (await db.execute(select(GradingRun).where(GradingRun.id == body.grading_run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
        if not r:
            raise NotFoundError("Grading run not found.")
    prefix = _PREFIXES[body.kind]
    safe_name = body.filename.replace("/", "_").replace("..", "_")
    key = f"{prefix}/{user.sub}/{uuid.uuid4()}/{safe_name}"
    minio = get_minio()
    url = minio.presigned_put(key, expires=timedelta(minutes=10))
    return PresignResponse(
        upload_url=url,
        storage_key=key,
        method="PUT",
        headers={"Content-Type": body.mime_type},
    )
