"""ME endpoints: /me, /me/dashboard."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import UnauthenticatedError
from app.models.class_ import Class
from app.models.class_subject import ClassSubject
from app.models.exam import Exam
from app.models.grading import GradingItem, GradingRun
from app.models.student import Student
from app.models.subject import Subject
from app.modules.auth.schemas import UserOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.sub, email=user.email, full_name=user.name)


@router.get("/dashboard")
async def dashboard(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    owner = user.sub
    subj = (await db.execute(select(func.count()).select_from(Subject).where(Subject.owner_id == owner, Subject.deleted_at.is_(None)))).scalar_one()
    cls = (await db.execute(select(func.count()).select_from(Class).where(Class.owner_id == owner, Class.deleted_at.is_(None)))).scalar_one()
    stu = (await db.execute(select(func.count()).select_from(Student).where(Student.owner_id == owner, Student.deleted_at.is_(None)))).scalar_one()
    exm = (await db.execute(select(func.count()).select_from(Exam).where(Exam.owner_id == owner, Exam.deleted_at.is_(None)))).scalar_one()
    grn = (await db.execute(select(func.count()).select_from(GradingRun).where(GradingRun.owner_id == owner, GradingRun.deleted_at.is_(None)))).scalar_one()
    flagged = (await db.execute(
        select(func.count()).select_from(GradingItem).where(
            GradingItem.owner_id == owner, GradingItem.flagged.is_(True), GradingItem.finalized.is_(False)
        )
    )).scalar_one()
    return {
        "subjects": subj,
        "classes": cls,
        "students": stu,
        "exams": exm,
        "grading_runs": grn,
        "flagged_items": flagged,
    }
