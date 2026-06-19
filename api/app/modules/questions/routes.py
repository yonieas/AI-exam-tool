"""Question routes."""
from __future__ import annotations

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models.exam import Exam
from app.models.question import Question
from app.modules.questions.schemas import QuestionCreate, QuestionOut, QuestionUpdate

router = APIRouter(prefix="/exams", tags=["questions"])


def _to_dto(q: Question) -> QuestionOut:
    return QuestionOut.model_validate(q)


@router.get("/{exam_id}/questions", response_model=dict)
async def list_questions(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    rows = (await db.execute(select(Question).where(Question.exam_id == exam_id).order_by(Question.position))).scalars().all()
    return {"data": [_to_dto(r).model_dump(mode="json") for r in rows]}


@router.post("/{exam_id}/questions", response_model=QuestionOut, status_code=201)
async def create_question(
    exam_id: UUID, body: QuestionCreate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestionOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    if e.status not in {"draft", "in_review"}:
        raise ConflictError("Cannot add questions to a finalized exam.")
    # Determine next position
    from sqlalchemy import func
    max_pos = (await db.execute(select(func.max(Question.position)).where(Question.exam_id == exam_id))).scalar() or 0
    if body.type == "mcq":
        # Validate: exactly one correct
        choices = body.options.get("choices", []) if isinstance(body.options, dict) else []
        if not any(c.get("is_correct") for c in choices):
            raise BadRequestError("MCQ must have exactly one correct choice.")
    q = Question(
        id=uuid.uuid4(),
        owner_id=user.sub,
        exam_id=exam_id,
        position=max_pos + 1,
        type=body.type,
        prompt=body.prompt.strip(),
        options=body.options or {},
        rubric=body.rubric,
        max_score=body.max_score,
        status="draft",
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return _to_dto(q)


@router.get("/{exam_id}/questions/{question_id}", response_model=QuestionOut)
async def get_question(
    exam_id: UUID, question_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestionOut:
    q = (await db.execute(
        select(Question).where(Question.id == question_id, Question.exam_id == exam_id, Question.owner_id == user.sub)
    )).scalar_one_or_none()
    if not q:
        raise NotFoundError("Question not found.")
    return _to_dto(q)


@router.patch("/{exam_id}/questions/{question_id}", response_model=QuestionOut)
async def update_question(
    exam_id: UUID, question_id: UUID, body: QuestionUpdate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestionOut:
    q = (await db.execute(
        select(Question).where(Question.id == question_id, Question.exam_id == exam_id, Question.owner_id == user.sub)
    )).scalar_one_or_none()
    if not q:
        raise NotFoundError("Question not found.")
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if e and e.status == "published":
        raise ConflictError("Cannot edit questions on a published exam.")
    if body.type is not None:
        q.type = body.type
    if body.prompt is not None:
        q.prompt = body.prompt.strip()
    if body.options is not None:
        q.options = body.options
    if body.rubric is not None:
        q.rubric = body.rubric
    if body.max_score is not None:
        q.max_score = body.max_score
    # Editing pushes an approved question back to in_review
    if q.status == "approved":
        q.status = "in_review"
    await db.commit()
    await db.refresh(q)
    return _to_dto(q)


@router.post("/{exam_id}/questions/{question_id}/approve", response_model=QuestionOut)
async def approve_question(
    exam_id: UUID, question_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestionOut:
    q = (await db.execute(
        select(Question).where(Question.id == question_id, Question.exam_id == exam_id, Question.owner_id == user.sub)
    )).scalar_one_or_none()
    if not q:
        raise NotFoundError("Question not found.")
    q.status = "approved"
    await db.commit()
    await db.refresh(q)
    return _to_dto(q)


@router.post("/{exam_id}/questions/{question_id}/reject", response_model=QuestionOut)
async def reject_question(
    exam_id: UUID, question_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestionOut:
    q = (await db.execute(
        select(Question).where(Question.id == question_id, Question.exam_id == exam_id, Question.owner_id == user.sub)
    )).scalar_one_or_none()
    if not q:
        raise NotFoundError("Question not found.")
    q.status = "draft"
    await db.commit()
    await db.refresh(q)
    return _to_dto(q)
