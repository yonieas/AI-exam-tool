"""Subject routes — owner-scoped CRUD."""
from __future__ import annotations

import uuid
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import ConflictError, NotFoundError
from app.models.subject import Subject
from app.modules.subjects.schemas import SubjectCreate, SubjectOut, SubjectUpdate
from app.schemas import make_cursor, parse_cursor

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _to_dto(s: Subject) -> SubjectOut:
    return SubjectOut.model_validate(s)


@router.get("", response_model=dict)
async def list_subjects(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = None,
) -> dict:
    stmt = select(Subject).where(Subject.owner_id == user.sub, Subject.deleted_at.is_(None)).order_by(Subject.created_at.desc(), Subject.id)
    if cursor:
        try:
            last_id, _ = parse_cursor(cursor)
            stmt = stmt.where(Subject.id < last_id)
        except Exception:
            pass
    stmt = stmt.limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [_to_dto(r).model_dump(mode="json") for r in rows]
    next_cursor = make_cursor(rows[-1].id) if has_more and rows else None
    return {"data": data, "page": {"next_cursor": next_cursor, "limit": limit, "has_more": has_more}}


@router.post("", response_model=SubjectOut, status_code=201)
async def create_subject(
    body: SubjectCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubjectOut:
    s = Subject(id=uuid.uuid4(), owner_id=user.sub, name=body.name.strip(), code=body.code)
    db.add(s)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError(f"Subject with name '{body.name}' already exists.") from e
    await db.refresh(s)
    return _to_dto(s)


@router.get("/{subject_id}", response_model=SubjectOut)
async def get_subject(
    subject_id: UUID,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubjectOut:
    s = (await db.execute(select(Subject).where(Subject.id == subject_id, Subject.owner_id == user.sub, Subject.deleted_at.is_(None)))).scalar_one_or_none()
    if not s:
        raise NotFoundError("Subject not found.")
    return _to_dto(s)


@router.patch("/{subject_id}", response_model=SubjectOut)
async def update_subject(
    subject_id: UUID,
    body: SubjectUpdate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubjectOut:
    s = (await db.execute(select(Subject).where(Subject.id == subject_id, Subject.owner_id == user.sub, Subject.deleted_at.is_(None)))).scalar_one_or_none()
    if not s:
        raise NotFoundError("Subject not found.")
    if body.name is not None:
        s.name = body.name.strip()
    if body.code is not None:
        s.code = body.code
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError("Subject name conflicts with another subject.") from e
    await db.refresh(s)
    return _to_dto(s)


@router.delete("/{subject_id}", status_code=204)
async def delete_subject(
    subject_id: UUID,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    from datetime import datetime
    from sqlalchemy import update
    s = (await db.execute(select(Subject).where(Subject.id == subject_id, Subject.owner_id == user.sub, Subject.deleted_at.is_(None)))).scalar_one_or_none()
    if not s:
        raise NotFoundError("Subject not found.")
    # Check usage by exam
    from app.models.exam import Exam
    in_use = (await db.execute(select(Exam.id).where(Exam.subject_id == subject_id, Exam.deleted_at.is_(None)).limit(1))).scalar_one_or_none()
    if in_use:
        raise ConflictError("Subject is in use by one or more exams and cannot be deleted.")
    await db.execute(
        update(Subject).where(Subject.id == subject_id, Subject.owner_id == user.sub).values(deleted_at=datetime.utcnow())
    )
    await db.commit()
