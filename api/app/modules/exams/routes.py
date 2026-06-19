"""Exam routes — CRUD, generate, publish, file listing, PDF download."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models.ai_job import AIJob
from app.models.exam import Exam
from app.models.file_asset import FileAsset
from app.models.question import Question
from app.models.subject import Subject
from app.modules.exams.schemas import ExamCreate, ExamOut, ExamUpdate
from app.schemas import make_cursor, parse_cursor
from app.storage.minio_client import get_minio
from app.workers.ai_worker import get_worker

router = APIRouter(prefix="/exams", tags=["exams"])


def _to_dto(e: Exam, question_count: int = 0) -> ExamOut:
    return ExamOut(
        id=e.id,
        subject_id=e.subject_id,
        title=e.title,
        source_kind=e.source_kind or "none",
        units=e.units or [],
        question_type_mode=e.question_type_mode,
        total_count=e.total_count,
        mcq_count=e.mcq_count,
        essay_count=e.essay_count,
        generation_config=e.generation_config or {},
        source_file_id=e.source_file_id,
        answer_key=e.answer_key,
        questions_pdf_file_id=e.questions_pdf_file_id,
        answers_pdf_file_id=e.answers_pdf_file_id,
        status=e.status or "draft",
        ai_generated=bool(e.ai_generated),
        published_at=e.published_at,
        created_at=e.created_at,
        updated_at=e.updated_at,
        deleted_at=e.deleted_at,
        question_count=question_count,
    )


async def _ensure_subject_owner(db: AsyncSession, subject_id: UUID, owner_id: UUID) -> Subject:
    s = (await db.execute(
        select(Subject).where(Subject.id == subject_id, Subject.owner_id == owner_id, Subject.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not s:
        raise BadRequestError("Subject is invalid.")
    return s


@router.get("", response_model=dict)
async def list_exams(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = None,
    subject_id: Optional[UUID] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
) -> dict:
    stmt = select(Exam).where(Exam.owner_id == user.sub, Exam.deleted_at.is_(None)).order_by(Exam.created_at.desc(), Exam.id)
    if subject_id:
        stmt = stmt.where(Exam.subject_id == subject_id)
    if status:
        stmt = stmt.where(Exam.status == status)
    if q:
        stmt = stmt.where(Exam.title.ilike(f"%{q}%"))
    if cursor:
        try:
            last_id, _ = parse_cursor(cursor)
            stmt = stmt.where(Exam.id < last_id)
        except Exception:
            pass
    stmt = stmt.limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    # Question counts
    counts: dict[UUID, int] = {}
    if rows:
        eids = [e.id for e in rows]
        c_rows = (await db.execute(
            select(Question.exam_id, func.count()).where(Question.exam_id.in_(eids)).group_by(Question.exam_id)
        )).all()
        for eid, c in c_rows:
            counts[eid] = c
    data = [_to_dto(e, counts.get(e.id, 0)).model_dump(mode="json") for e in rows]
    next_cursor = make_cursor(rows[-1].id) if has_more and rows else None
    return {"data": data, "page": {"next_cursor": next_cursor, "limit": limit, "has_more": has_more}}


@router.post("", response_model=ExamOut, status_code=201)
async def create_exam(
    body: ExamCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExamOut:
    await _ensure_subject_owner(db, body.subject_id, user.sub)
    source_kind = body.source.kind if body.source else "none"
    e = Exam(
        id=uuid.uuid4(),
        owner_id=user.sub,
        subject_id=body.subject_id,
        title=body.title.strip(),
        source_kind=source_kind,
        units=body.units or [],
        question_type_mode=body.question_type_mode,
        total_count=body.total_count,
        mcq_count=body.mcq_count,
        essay_count=body.essay_count,
        generation_config=body.generation_config or {},
        source_file_id=body.source.file_asset_id if body.source else None,
        status="draft",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return _to_dto(e)


@router.get("/{exam_id}", response_model=ExamOut)
async def get_exam(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> ExamOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    qc = (await db.execute(select(func.count()).select_from(Question).where(Question.exam_id == e.id))).scalar_one()
    return _to_dto(e, qc)


@router.patch("/{exam_id}", response_model=ExamOut)
async def update_exam(
    exam_id: UUID, body: ExamUpdate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> ExamOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    if e.status != "draft":
        raise ConflictError("Cannot edit a non-draft exam.")
    if body.title is not None:
        e.title = body.title.strip()
    if body.units is not None:
        e.units = body.units
    if body.total_count is not None:
        e.total_count = body.total_count
    if body.mcq_count is not None:
        e.mcq_count = body.mcq_count
    if body.essay_count is not None:
        e.essay_count = body.essay_count
    if body.generation_config is not None:
        e.generation_config = body.generation_config
    await db.commit()
    await db.refresh(e)
    qc = (await db.execute(select(func.count()).select_from(Question).where(Question.exam_id == e.id))).scalar_one()
    return _to_dto(e, qc)


@router.delete("/{exam_id}", status_code=204)
async def delete_exam(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    await db.execute(update(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub).values(deleted_at=datetime.utcnow()))
    await db.commit()


@router.post("/{exam_id}/generate", status_code=202, response_model=dict)
async def generate_exam(
    exam_id: UUID,
    user: CurrentUser,
    idem_key: Annotated[str | None, Query(alias="Idempotency-Key")] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    idem = idem_key or str(uuid.uuid4())
    # Idempotency check
    existing = (await db.execute(
        select(AIJob).where(AIJob.owner_id == user.sub, AIJob.idempotency_key == idem)
    )).scalar_one_or_none()
    if existing:
        return {"ai_job": _ai_job_dto(existing)}
    job = AIJob(
        id=uuid.uuid4(),
        owner_id=user.sub,
        job_type="question_generation",
        job_status="queued",
        exam_id=exam_id,
        input_payload={"exam_id": str(exam_id)},
        idempotency_key=idem,
        ai_provider="mock",
        model="mock-minimax-m2.7",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    # For MVP: process synchronously in-process; in production this would enqueue
    # to BullMQ and a separate worker would consume. Keeping the in-process path
    # avoids the need for an external broker while staying within the spec's
    # "in-house asyncio worker" option (BACKEND_CONVENTIONS §13).
    try:
        from app.workers.ai_worker import process_one
        await process_one(str(job.id))
        await db.refresh(job)
    except Exception:
        logger.exception("AI job %s failed inline", job.id)
    return {"ai_job": _ai_job_dto(job)}


@router.post("/{exam_id}/publish", response_model=ExamOut)
async def publish_exam(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> ExamOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    qs = (await db.execute(select(Question).where(Question.exam_id == e.id))).scalars().all()
    if not qs:
        raise BadRequestError("Exam has no questions.")
    not_approved = [q for q in qs if q.status != "approved"]
    if not_approved:
        raise ConflictError(f"{len(not_approved)} questions are not yet approved.")
    e.status = "published"
    e.published_at = datetime.utcnow()
    # Render PDFs
    try:
        from app.modules.exams.pdf import render_exam_pdfs
        await render_exam_pdfs(db, e, qs)
    except Exception as ex:
        # Don't fail the publish on PDF error
        pass
    await db.commit()
    await db.refresh(e)
    qc = (await db.execute(select(func.count()).select_from(Question).where(Question.exam_id == e.id))).scalar_one()
    return _to_dto(e, qc)


@router.post("/{exam_id}/close", response_model=ExamOut)
async def close_exam(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> ExamOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    e.status = "closed"
    await db.commit()
    await db.refresh(e)
    qc = (await db.execute(select(func.count()).select_from(Question).where(Question.exam_id == e.id))).scalar_one()
    return _to_dto(e, qc)


def _ai_job_dto(job: AIJob) -> dict:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "job_status": job.job_status,
        "exam_id": str(job.exam_id) if job.exam_id else None,
        "grading_run_id": str(job.grading_run_id) if job.grading_run_id else None,
        "grading_item_id": str(job.grading_item_id) if job.grading_item_id else None,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
        "model": job.model,
        "ai_provider": job.ai_provider,
        "total_tokens_input": job.total_tokens_input,
        "total_tokens_output": job.total_tokens_output,
        "cost_usd_micro": job.cost_usd_micro,
        "poll_url": f"/api/v1/ai-jobs/{job.id}",
    }
