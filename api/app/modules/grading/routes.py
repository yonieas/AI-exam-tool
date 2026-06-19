"""Grading routes."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models.ai_job import AIJob
from app.models.exam import Exam
from app.models.file_asset import FileAsset
from app.models.grading import GradingItem, GradingItemResponse, GradingRun
from app.models.question import Question
from app.models.student import Student
from app.modules.grading.schemas import (
    GradingFinalizeResponse,
    GradingItemCreate,
    GradingItemDetail,
    GradingItemOut,
    GradingOverride,
    GradingResponseOut,
    GradingRunCreate,
    GradingRunOut,
)
from app.schemas import make_cursor, parse_cursor
from app.workers.ai_worker import get_worker

router = APIRouter(prefix="/grading-runs", tags=["grading"])


def _run_dto(r: GradingRun, item_count: int, flagged_count: int, finalized_count: int) -> GradingRunOut:
    return GradingRunOut(
        id=r.id, exam_id=r.exam_id, title=r.title,
        benchmark_kind=r.benchmark_kind, benchmark_file_id=r.benchmark_file_id,
        status=r.status, max_score_total=r.max_score_total,
        finalized_at=r.finalized_at,
        created_at=r.created_at, updated_at=r.updated_at,
        item_count=item_count, flagged_count=flagged_count, finalized_count=finalized_count,
    )


async def _counts_for_run(db: AsyncSession, run_id: UUID) -> tuple[int, int, int]:
    total = (await db.execute(select(func.count()).select_from(GradingItem).where(GradingItem.grading_run_id == run_id))).scalar_one()
    flagged = (await db.execute(select(func.count()).select_from(GradingItem).where(GradingItem.grading_run_id == run_id, GradingItem.flagged.is_(True), GradingItem.finalized.is_(False)))).scalar_one()
    finalized = (await db.execute(select(func.count()).select_from(GradingItem).where(GradingItem.grading_run_id == run_id, GradingItem.finalized.is_(True)))).scalar_one()
    return int(total), int(flagged), int(finalized)


@router.get("", response_model=dict)
async def list_runs(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = None,
    exam_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> dict:
    stmt = select(GradingRun).where(GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)).order_by(GradingRun.created_at.desc(), GradingRun.id)
    if exam_id:
        stmt = stmt.where(GradingRun.exam_id == exam_id)
    if status:
        stmt = stmt.where(GradingRun.status == status)
    if cursor:
        try:
            last_id, _ = parse_cursor(cursor)
            stmt = stmt.where(GradingRun.id < last_id)
        except Exception:
            pass
    stmt = stmt.limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = []
    for r in rows:
        ic, fc, fnc = await _counts_for_run(db, r.id)
        data.append(_run_dto(r, ic, fc, fnc).model_dump(mode="json"))
    next_cursor = make_cursor(rows[-1].id) if has_more and rows else None
    return {"data": data, "page": {"next_cursor": next_cursor, "limit": limit, "has_more": has_more}}


@router.post("", response_model=GradingRunOut, status_code=201)
async def create_run(
    body: GradingRunCreate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> GradingRunOut:
    e = (await db.execute(select(Exam).where(Exam.id == body.exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    if body.benchmark_kind == "uploaded" and not body.benchmark_file_id:
        raise BadRequestError("benchmark_file_id is required for uploaded benchmark.")
    qs = (await db.execute(select(Question).where(Question.exam_id == e.id))).scalars().all()
    max_total = sum((float(q.max_score) for q in qs), 0.0)
    r = GradingRun(
        id=uuid.uuid4(),
        owner_id=user.sub,
        exam_id=body.exam_id,
        title=body.title.strip(),
        benchmark_kind=body.benchmark_kind,
        benchmark_file_id=body.benchmark_file_id,
        status="draft",
        max_score_total=Decimal(str(round(max_total, 2))),
    )
    db.add(r)
    await db.flush()
    # Pre-create grading_items for selected students
    if body.student_ids:
        for sid in body.student_ids:
            # The file will be added later; create a placeholder item with status=pending
            gi = GradingItem(
                id=uuid.uuid4(),
                owner_id=user.sub,
                grading_run_id=r.id,
                student_id=sid,
                answer_file_id=uuid.uuid4(),  # placeholder; will be replaced when file uploaded
                status="pending",
                max_score_total=Decimal(str(round(max_total, 2))),
            )
            db.add(gi)
    await db.commit()
    await db.refresh(r)
    ic, fc, fnc = await _counts_for_run(db, r.id)
    return _run_dto(r, ic, fc, fnc)


@router.get("/{run_id}", response_model=GradingRunOut)
async def get_run(
    run_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> GradingRunOut:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    ic, fc, fnc = await _counts_for_run(db, r.id)
    return _run_dto(r, ic, fc, fnc)


@router.delete("/{run_id}", status_code=204)
async def delete_run(
    run_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    if r.status == "finalized":
        raise ConflictError("Cannot delete a finalized run.")
    await db.execute(update(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub).values(deleted_at=datetime.utcnow()))
    await db.commit()


@router.post("/{run_id}/items", status_code=202, response_model=dict)
async def register_item(
    run_id: UUID,
    body: GradingItemCreate,
    user: CurrentUser,
    idem_key: Annotated[str | None, Query(alias="Idempotency-Key")] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    student = (await db.execute(select(Student).where(Student.id == body.student_id, Student.owner_id == user.sub, Student.deleted_at.is_(None)))).scalar_one_or_none()
    if not student:
        raise BadRequestError("Student is invalid.")
    fa = (await db.execute(select(FileAsset).where(FileAsset.id == body.file_asset_id, FileAsset.owner_id == user.sub, FileAsset.deleted_at.is_(None)))).scalar_one_or_none()
    if not fa:
        raise BadRequestError("File asset is invalid.")
    if fa.kind != "student_answer":
        raise BadRequestError("File asset must be a student answer.")
    # Idempotency
    idem = idem_key or str(uuid.uuid4())
    existing = (await db.execute(
        select(AIJob).where(AIJob.owner_id == user.sub, AIJob.idempotency_key == idem)
    )).scalar_one_or_none()
    if existing:
        return {"ai_job": _ai_job_dto(existing)}
    # Upsert grading item
    existing_item = (await db.execute(
        select(GradingItem).where(GradingItem.grading_run_id == run_id, GradingItem.student_id == body.student_id)
    )).scalar_one_or_none()
    if existing_item:
        existing_item.answer_file_id = fa.id
        existing_item.status = "ai_processing"
        gi_id = existing_item.id
    else:
        gi = GradingItem(
            id=uuid.uuid4(),
            owner_id=user.sub,
            grading_run_id=run_id,
            student_id=body.student_id,
            answer_file_id=fa.id,
            status="ai_processing",
            max_score_total=r.max_score_total,
        )
        db.add(gi)
        await db.flush()
        gi_id = gi.id
    # Create AI job
    job = AIJob(
        id=uuid.uuid4(),
        owner_id=user.sub,
        job_type="grading",
        job_status="queued",
        exam_id=r.exam_id,
        grading_run_id=run_id,
        grading_item_id=gi_id,
        input_payload={"grading_item_id": str(gi_id)},
        idempotency_key=idem,
        ai_provider="mock",
        model="mock-minimax-m2.7",
    )
    db.add(job)
    # Link file to the grading item
    fa.grading_item_id = gi_id
    fa.grading_run_id = run_id
    r.status = "grading"
    await db.commit()
    await db.refresh(job)
    worker = get_worker()
    await worker.enqueue(job.id)
    return {"ai_job": _ai_job_dto(job)}


@router.get("/{run_id}/items", response_model=dict)
async def list_items(
    run_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    rows = (await db.execute(
        select(GradingItem, Student)
        .join(Student, Student.id == GradingItem.student_id)
        .where(GradingItem.grading_run_id == run_id)
        .order_by(Student.name)
    )).all()
    data = []
    for gi, s in rows:
        d = GradingItemOut(
            id=gi.id, grading_run_id=gi.grading_run_id, student_id=gi.student_id,
            student_name=s.name, answer_file_id=gi.answer_file_id, status=gi.status,
            total_score=gi.total_score, max_score_total=gi.max_score_total,
            flagged=gi.flagged, finalized=gi.finalized,
            created_at=gi.created_at, updated_at=gi.updated_at,
        )
        data.append(d.model_dump(mode="json"))
    return {"data": data}


@router.get("/{run_id}/items/{item_id}", response_model=GradingItemDetail)
async def get_item(
    run_id: UUID, item_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> GradingItemDetail:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    gi = (await db.execute(
        select(GradingItem).where(GradingItem.id == item_id, GradingItem.grading_run_id == run_id, GradingItem.owner_id == user.sub)
    )).scalar_one_or_none()
    if not gi:
        raise NotFoundError("Grading item not found.")
    s = (await db.execute(select(Student).where(Student.id == gi.student_id))).scalar_one_or_none()
    responses = (await db.execute(
        select(GradingItemResponse, Question)
        .join(Question, Question.id == GradingItemResponse.question_id)
        .where(GradingItemResponse.grading_item_id == gi.id)
        .order_by(Question.position)
    )).all()
    resps = []
    for resp, q in responses:
        resps.append(GradingResponseOut(
            id=resp.id, grading_item_id=resp.grading_item_id, question_id=resp.question_id,
            question_position=q.position, question_prompt=q.prompt, question_max_score=q.max_score,
            answer_text=resp.answer_text, ai_score=resp.ai_score, max_score=resp.max_score,
            teacher_score=resp.teacher_score, confidence=resp.confidence, flagged=resp.flagged,
            ai_rationale=resp.ai_rationale, teacher_rationale=resp.teacher_rationale,
            overridden=resp.overridden, graded_at=resp.graded_at, reviewed_at=resp.reviewed_at,
        ))
    return GradingItemDetail(
        id=gi.id, grading_run_id=gi.grading_run_id, student_id=gi.student_id,
        student_name=s.name if s else None, answer_file_id=gi.answer_file_id,
        status=gi.status, total_score=gi.total_score, max_score_total=gi.max_score_total,
        flagged=gi.flagged, finalized=gi.finalized,
        created_at=gi.created_at, updated_at=gi.updated_at, responses=resps,
    )


@router.patch("/{run_id}/items/{item_id}/responses/{response_id}", response_model=GradingResponseOut)
async def override_response(
    run_id: UUID, item_id: UUID, response_id: UUID, body: GradingOverride,
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> GradingResponseOut:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    gi = (await db.execute(select(GradingItem).where(GradingItem.id == item_id, GradingItem.grading_run_id == run_id, GradingItem.owner_id == user.sub))).scalar_one_or_none()
    if not gi:
        raise NotFoundError("Grading item not found.")
    resp = (await db.execute(
        select(GradingItemResponse).where(
            GradingItemResponse.id == response_id,
            GradingItemResponse.grading_item_id == gi.id,
        )
    )).scalar_one_or_none()
    if not resp:
        raise NotFoundError("Response not found.")
    if body.teacher_score < 0 or body.teacher_score > resp.max_score:
        raise BadRequestError(f"teacher_score must be in [0, {resp.max_score}].")
    resp.teacher_score = body.teacher_score
    resp.teacher_rationale = body.teacher_rationale
    resp.overridden = True
    resp.reviewed_at = datetime.utcnow()
    await db.commit()
    # Recompute item totals
    await _recompute_item(db, gi, r)
    await db.refresh(resp)
    q = (await db.execute(select(Question).where(Question.id == resp.question_id))).scalar_one_or_none()
    return GradingResponseOut(
        id=resp.id, grading_item_id=resp.grading_item_id, question_id=resp.question_id,
        question_position=q.position if q else None, question_prompt=q.prompt if q else None,
        question_max_score=q.max_score if q else None,
        answer_text=resp.answer_text, ai_score=resp.ai_score, max_score=resp.max_score,
        teacher_score=resp.teacher_score, confidence=resp.confidence, flagged=resp.flagged,
        ai_rationale=resp.ai_rationale, teacher_rationale=resp.teacher_rationale,
        overridden=resp.overridden, graded_at=resp.graded_at, reviewed_at=resp.reviewed_at,
    )


@router.post("/{run_id}/items/{item_id}/waive-flag", response_model=GradingItemDetail)
async def waive_item_flag(
    run_id: UUID, item_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> GradingItemDetail:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    gi = (await db.execute(select(GradingItem).where(GradingItem.id == item_id, GradingItem.grading_run_id == run_id, GradingItem.owner_id == user.sub))).scalar_one_or_none()
    if not gi:
        raise NotFoundError("Grading item not found.")
    # Approve all flagged responses
    responses = (await db.execute(
        select(GradingItemResponse).where(GradingItemResponse.grading_item_id == gi.id, GradingItemResponse.flagged.is_(True))
    )).scalars().all()
    for resp in responses:
        resp.flagged = False
        resp.reviewed_at = datetime.utcnow()
    await db.commit()
    await _recompute_item(db, gi, r)
    return await get_item(run_id, item_id, user, db)


@router.post("/{run_id}/finalize", response_model=GradingFinalizeResponse)
async def finalize_run(
    run_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> GradingFinalizeResponse:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    if r.status == "finalized":
        return GradingFinalizeResponse(
            id=r.id, status=r.status, finalized_at=r.finalized_at,
            summary=await _summary(db, r),
        )
    items = (await db.execute(select(GradingItem).where(GradingItem.grading_run_id == run_id))).scalars().all()
    blocking = [i for i in items if i.flagged and not i.finalized]
    if blocking:
        raise ConflictError(
            f"{len(blocking)} flagged item(s) still need review.",
            errors=[{"item_id": str(i.id), "student_id": str(i.student_id)} for i in blocking],
        )
    pending = [i for i in items if i.status not in {"ai_done", "reviewed", "final"}]
    if pending:
        raise ConflictError(f"{len(pending)} item(s) are not graded yet.")
    r.status = "finalized"
    r.finalized_at = datetime.utcnow()
    for i in items:
        i.finalized = True
    await db.commit()
    await db.refresh(r)
    return GradingFinalizeResponse(id=r.id, status=r.status, finalized_at=r.finalized_at, summary=await _summary(db, r))


@router.get("/{run_id}/results.csv")
async def results_csv(
    run_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    rows = (await db.execute(
        select(GradingItem, Student)
        .join(Student, Student.id == GradingItem.student_id)
        .where(GradingItem.grading_run_id == run_id)
        .order_by(Student.name)
    )).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["student_id", "student_name", "student_code", "total_score", "max_score", "pct", "status", "flagged"])
    for gi, s in rows:
        total = float(gi.total_score) if gi.total_score is not None else 0.0
        max_total = float(gi.max_score_total) if gi.max_score_total else 0.0
        pct = round((total / max_total * 100), 2) if max_total else 0.0
        w.writerow([str(s.id), s.name, s.student_code or "", total, max_total, pct, gi.status, "yes" if gi.flagged else "no"])
    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{r.title}_results.csv"'})


async def _summary(db: AsyncSession, r: GradingRun) -> dict:
    items = (await db.execute(select(GradingItem).where(GradingItem.grading_run_id == r.id))).scalars().all()
    scores = [float(i.total_score) for i in items if i.total_score is not None]
    if not scores:
        return {"n_items": len(items), "mean": 0, "median": 0}
    scores.sort()
    mean = sum(scores) / len(scores)
    mid = scores[len(scores) // 2]
    return {"n_items": len(items), "mean": round(mean, 3), "median": round(mid, 3)}


async def _recompute_item(db: AsyncSession, gi: GradingItem, r: GradingRun) -> None:
    responses = (await db.execute(
        select(GradingItemResponse).where(GradingItemResponse.grading_item_id == gi.id)
    )).scalars().all()
    total = 0.0
    max_total = 0.0
    any_flagged_unreviewed = False
    for resp in responses:
        score = float(resp.teacher_score) if resp.teacher_score is not None else (float(resp.ai_score) if resp.ai_score is not None else 0.0)
        total += score
        max_total += float(resp.max_score)
        if resp.flagged and not resp.overridden:
            any_flagged_unreviewed = True
    gi.total_score = round(total, 2)
    gi.max_score_total = round(max_total, 2)
    gi.flagged = any_flagged_unreviewed
    # If all responses have been reviewed/overridden, mark as reviewed
    if any(resp.overridden for resp in responses) and not any_flagged_unreviewed:
        gi.status = "reviewed"
    # Update run status
    items = (await db.execute(select(GradingItem).where(GradingItem.grading_run_id == r.id))).scalars().all()
    if all(i.status in {"reviewed", "final"} or (i.status == "ai_done" and not i.flagged) for i in items):
        r.status = "needs_review" if any(i.flagged for i in items) else "grading"
    await db.commit()


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
