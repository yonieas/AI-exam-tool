"""Student routes (incl. Excel import)."""
from __future__ import annotations

import io
import uuid
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, NotFoundError
from app.models.student import Student
from app.modules.students.excel import parse_preview, parse_rows
from app.modules.students.schemas import (
    ImportPreviewResponse,
    ImportRequest,
    ImportResponse,
    StudentCreate,
    StudentOut,
    StudentUpdate,
)
from app.schemas import make_cursor, parse_cursor

router = APIRouter(prefix="/students", tags=["students"])


def _to_dto(s: Student) -> StudentOut:
    return StudentOut.model_validate(s)


@router.get("", response_model=dict)
async def list_students(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = None,
    class_id: Optional[UUID] = None,
) -> dict:
    stmt = select(Student).where(Student.owner_id == user.sub, Student.deleted_at.is_(None)).order_by(Student.created_at.desc(), Student.id)
    if class_id:
        from app.models.class_enrollment import ClassEnrollment
        stmt = stmt.join(ClassEnrollment, ClassEnrollment.student_id == Student.id).where(
            ClassEnrollment.class_id == class_id, ClassEnrollment.deleted_at.is_(None)
        )
    if cursor:
        try:
            last_id, _ = parse_cursor(cursor)
            stmt = stmt.where(Student.id < last_id)
        except Exception:
            pass
    stmt = stmt.limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().unique().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [_to_dto(r).model_dump(mode="json") for r in rows]
    next_cursor = make_cursor(rows[-1].id) if has_more and rows else None
    return {"data": data, "page": {"next_cursor": next_cursor, "limit": limit, "has_more": has_more}}


@router.post("", response_model=StudentOut, status_code=201)
async def create_student(
    body: StudentCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentOut:
    s = Student(
        id=uuid.uuid4(),
        owner_id=user.sub,
        name=body.name.strip(),
        student_code=body.student_code,
        email=body.email.lower() if body.email else None,
        extra_columns=body.extra_columns or {},
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _to_dto(s)


@router.get("/{student_id}", response_model=StudentOut)
async def get_student(student_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> StudentOut:
    s = (await db.execute(select(Student).where(Student.id == student_id, Student.owner_id == user.sub, Student.deleted_at.is_(None)))).scalar_one_or_none()
    if not s:
        raise NotFoundError("Student not found.")
    return _to_dto(s)


@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: UUID, body: StudentUpdate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentOut:
    s = (await db.execute(select(Student).where(Student.id == student_id, Student.owner_id == user.sub, Student.deleted_at.is_(None)))).scalar_one_or_none()
    if not s:
        raise NotFoundError("Student not found.")
    if body.name is not None:
        s.name = body.name.strip()
    if body.student_code is not None:
        s.student_code = body.student_code
    if body.email is not None:
        s.email = body.email.lower() if body.email else None
    if body.extra_columns is not None:
        s.extra_columns = body.extra_columns
    await db.commit()
    await db.refresh(s)
    return _to_dto(s)


@router.delete("/{student_id}", status_code=204)
async def delete_student(student_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    s = (await db.execute(select(Student).where(Student.id == student_id, Student.owner_id == user.sub, Student.deleted_at.is_(None)))).scalar_one_or_none()
    if not s:
        raise NotFoundError("Student not found.")
    await db.execute(update(Student).where(Student.id == student_id, Student.owner_id == user.sub).values(deleted_at=datetime.utcnow()))
    await db.commit()


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(
    user: CurrentUser,
    file: UploadFile = File(...),
) -> ImportPreviewResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise BadRequestError("Upload a .xlsx file.")
    data = await file.read()
    parsed = parse_preview(data)
    return ImportPreviewResponse.model_validate(parsed)


@router.post("/import", response_model=ImportResponse)
async def import_students(
    user: CurrentUser,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    rows: str = Form(default="process_all"),
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise BadRequestError("Upload a .xlsx file.")
    import json
    try:
        mapping_obj = json.loads(mapping)
    except json.JSONDecodeError as e:
        raise BadRequestError(f"Invalid mapping JSON: {e}") from e
    if "name" not in mapping_obj:
        raise BadRequestError("Mapping must include a 'name' column letter.")
    data = await file.read()
    parsed = parse_rows(data)
    if not parsed:
        return ImportResponse(imported=0, skipped=0)
    headers, *data_rows = parsed
    # Build column-letter → header lookup
    letter_to_header = {}
    for i, h in enumerate(headers):
        from openpyxl.utils import get_column_letter
        letter_to_header[get_column_letter(i + 1)] = h
    # Build canonical-field → column letter
    name_letter = mapping_obj["name"]
    code_letter = mapping_obj.get("student_code")
    email_letter = mapping_obj.get("email")
    extras = mapping_obj.get("extra_columns") or {}
    # Optional: rows filter
    row_filter = None
    if rows != "process_all":
        try:
            row_filter = set(int(x) for x in json.loads(rows))
        except Exception:
            row_filter = None

    from openpyxl.utils import column_index_from_string
    name_idx = column_index_from_string(name_letter) - 1

    def _col_idx(letter):
        return column_index_from_string(letter) - 1

    imported = 0
    skipped = 0
    errors: list[dict] = []
    for row_idx, row in enumerate(data_rows):
        if row_filter is not None and row_idx not in row_filter:
            continue
        try:
            name_val = (row[name_idx] if name_idx < len(row) else "") or ""
            name_val = str(name_val).strip()
            if not name_val:
                skipped += 1
                errors.append({"row": row_idx, "message": "Empty name; skipped."})
                continue
            code_val = str(row[_col_idx(code_letter)]).strip() if code_letter and _col_idx(code_letter) < len(row) and row[_col_idx(code_letter)] else None
            email_val = str(row[_col_idx(email_letter)]).strip().lower() if email_letter and _col_idx(email_letter) < len(row) and row[_col_idx(email_letter)] else None
            extras_dict = {}
            for extra_name, letter in extras.items():
                idx = _col_idx(letter)
                if idx < len(row) and row[idx]:
                    extras_dict[extra_name] = str(row[idx])
            s = Student(
                id=uuid.uuid4(),
                owner_id=user.sub,
                name=name_val,
                student_code=code_val,
                email=email_val,
                extra_columns=extras_dict,
            )
            db.add(s)
            imported += 1
        except Exception as e:
            errors.append({"row": row_idx, "message": str(e)})
            skipped += 1
    await db.commit()
    return ImportResponse(imported=imported, skipped=skipped, errors=errors)
