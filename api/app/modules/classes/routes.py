"""Class routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models.class_ import Class
from app.models.class_subject import ClassSubject
from app.models.student import Student
from app.models.class_enrollment import ClassEnrollment
from app.models.subject import Subject
from app.modules.classes.schemas import (
    ClassCreate,
    ClassEnrollmentCreate,
    ClassOut,
    ClassSubjectAssign,
    ClassUpdate,
)
from app.schemas import make_cursor, parse_cursor

router = APIRouter(prefix="/classes", tags=["classes"])


async def _class_dto(db: AsyncSession, c: Class) -> ClassOut:
    subject_ids = [r.subject_id for r in (await db.execute(select(ClassSubject.subject_id).where(ClassSubject.class_id == c.id))).all()]
    student_count = (await db.execute(
        select(func.count()).select_from(ClassEnrollment).where(ClassEnrollment.class_id == c.id, ClassEnrollment.deleted_at.is_(None))
    )).scalar_one()
    return ClassOut(
        id=c.id, name=c.name, grade_level=c.grade_level,
        subject_ids=subject_ids, student_count=student_count,
        created_at=c.created_at, updated_at=c.updated_at, deleted_at=c.deleted_at,
    )


@router.get("", response_model=dict)
async def list_classes(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = None,
    subject_id: Optional[UUID] = None,
) -> dict:
    stmt = select(Class).where(Class.owner_id == user.sub, Class.deleted_at.is_(None)).order_by(Class.created_at.desc(), Class.id)
    if subject_id:
        stmt = stmt.join(ClassSubject, ClassSubject.class_id == Class.id).where(ClassSubject.subject_id == subject_id)
    if cursor:
        try:
            last_id, _ = parse_cursor(cursor)
            stmt = stmt.where(Class.id < last_id)
        except Exception:
            pass
    stmt = stmt.limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().unique().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [(await _class_dto(db, c)).model_dump(mode="json") for c in rows]
    next_cursor = make_cursor(rows[-1].id) if has_more and rows else None
    return {"data": data, "page": {"next_cursor": next_cursor, "limit": limit, "has_more": has_more}}


@router.post("", response_model=ClassOut, status_code=201)
async def create_class(
    body: ClassCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassOut:
    # Verify subjects are owned by caller
    if body.subject_ids:
        found = (await db.execute(
            select(Subject.id).where(Subject.id.in_(body.subject_ids), Subject.owner_id == user.sub, Subject.deleted_at.is_(None))
        )).scalars().all()
        if len(found) != len(set(body.subject_ids)):
            raise BadRequestError("One or more subject_ids are invalid.")
    c = Class(id=uuid.uuid4(), owner_id=user.sub, name=body.name.strip(), grade_level=body.grade_level)
    db.add(c)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError(f"Class with name '{body.name}' already exists.") from e
    for sid in body.subject_ids:
        db.add(ClassSubject(class_id=c.id, subject_id=sid, owner_id=user.sub))
    await db.commit()
    await db.refresh(c)
    return await _class_dto(db, c)


@router.get("/{class_id}", response_model=ClassOut)
async def get_class(
    class_id: UUID,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassOut:
    c = (await db.execute(select(Class).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    return await _class_dto(db, c)


@router.patch("/{class_id}", response_model=ClassOut)
async def update_class(
    class_id: UUID,
    body: ClassUpdate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassOut:
    c = (await db.execute(select(Class).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    if body.name is not None:
        c.name = body.name.strip()
    if body.grade_level is not None:
        c.grade_level = body.grade_level
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError("Class name conflicts.") from e
    await db.refresh(c)
    return await _class_dto(db, c)


@router.delete("/{class_id}", status_code=204)
async def delete_class(
    class_id: UUID,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    c = (await db.execute(select(Class).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    await db.execute(update(Class).where(Class.id == class_id, Class.owner_id == user.sub).values(deleted_at=datetime.utcnow()))
    await db.commit()


@router.get("/{class_id}/subjects", response_model=list[UUID])
async def list_class_subjects(
    class_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UUID]:
    c = (await db.execute(select(Class.id).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    rows = (await db.execute(select(ClassSubject.subject_id).where(ClassSubject.class_id == class_id))).all()
    return [r[0] for r in rows]


@router.put("/{class_id}/subjects", response_model=list[UUID])
async def set_class_subjects(
    class_id: UUID,
    body: ClassSubjectAssign,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UUID]:
    c = (await db.execute(select(Class).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    if body.subject_ids:
        found = (await db.execute(
            select(Subject.id).where(Subject.id.in_(body.subject_ids), Subject.owner_id == user.sub, Subject.deleted_at.is_(None))
        )).scalars().all()
        if len(found) != len(set(body.subject_ids)):
            raise BadRequestError("One or more subject_ids are invalid.")
    await db.execute(delete(ClassSubject).where(ClassSubject.class_id == class_id))
    for sid in body.subject_ids:
        db.add(ClassSubject(class_id=class_id, subject_id=sid, owner_id=user.sub))
    await db.commit()
    return list(set(body.subject_ids))


@router.get("/{class_id}/students", response_model=list[dict])
async def list_class_students(
    class_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    c = (await db.execute(select(Class.id).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    rows = (await db.execute(
        select(Student)
        .join(ClassEnrollment, ClassEnrollment.student_id == Student.id)
        .where(ClassEnrollment.class_id == class_id, ClassEnrollment.deleted_at.is_(None), Student.deleted_at.is_(None))
    )).scalars().all()
    return [{"id": str(s.id), "name": s.name, "student_code": s.student_code, "email": s.email} for s in rows]


@router.post("/{class_id}/enrollments", status_code=201)
async def enroll_student(
    class_id: UUID,
    body: ClassEnrollmentCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    c = (await db.execute(select(Class.id).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    student = (await db.execute(select(Student).where(Student.id == body.student_id, Student.owner_id == user.sub, Student.deleted_at.is_(None)))).scalar_one_or_none()
    if not student:
        raise BadRequestError("Student is invalid.")
    # Idempotent: if there's a soft-deleted enrollment, re-create it.
    existing = (await db.execute(
        select(ClassEnrollment).where(ClassEnrollment.class_id == class_id, ClassEnrollment.student_id == body.student_id)
    )).scalar_one_or_none()
    if existing and not existing.deleted_at:
        return {"id": str(existing.id), "class_id": str(class_id), "student_id": str(body.student_id)}
    if existing:
        existing.deleted_at = None
        existing.enrolled_at = datetime.utcnow()
    else:
        db.add(ClassEnrollment(id=uuid.uuid4(), owner_id=user.sub, class_id=class_id, student_id=body.student_id))
    await db.commit()
    return {"class_id": str(class_id), "student_id": str(body.student_id)}


@router.delete("/{class_id}/enrollments/{student_id}", status_code=204)
async def unenroll_student(
    class_id: UUID, student_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    c = (await db.execute(select(Class.id).where(Class.id == class_id, Class.owner_id == user.sub, Class.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise NotFoundError("Class not found.")
    await db.execute(
        update(ClassEnrollment)
        .where(ClassEnrollment.class_id == class_id, ClassEnrollment.student_id == student_id, ClassEnrollment.owner_id == user.sub)
        .values(deleted_at=datetime.utcnow())
    )
    await db.commit()
