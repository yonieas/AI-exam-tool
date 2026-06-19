"""File routes (per-exam, per-run)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import BadRequestError, NotFoundError
from app.models.exam import Exam
from app.models.file_asset import FileAsset
from app.models.grading import GradingRun
from app.modules.files.schemas import FileAssetOut, FileAssetRegister, FileAssetRename
from app.storage.minio_client import get_minio

# Two routers: per-exam and per-run
exam_router = APIRouter(prefix="/exams", tags=["files"])
run_router = APIRouter(prefix="/grading-runs", tags=["files"])


@exam_router.get("/{exam_id}/files", response_model=dict)
async def list_exam_files(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    rows = (await db.execute(
        select(FileAsset).where(FileAsset.exam_id == exam_id, FileAsset.deleted_at.is_(None)).order_by(FileAsset.created_at)
    )).scalars().all()
    return {"data": [FileAssetOut.model_validate(r).model_dump(mode="json") for r in rows]}


@exam_router.post("/{exam_id}/files", response_model=FileAssetOut, status_code=201)
async def register_exam_file(
    exam_id: UUID, body: FileAssetRegister, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> FileAssetOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    valid_kinds = {"source_image", "source_pdf", "questions_pdf", "answers_pdf", "benchmark_pdf", "benchmark_image"}
    if body.kind not in valid_kinds:
        raise BadRequestError(f"Invalid kind for exam file: {body.kind}")
    fa = FileAsset(
        id=uuid.uuid4(),
        owner_id=user.sub,
        exam_id=exam_id,
        kind=body.kind,
        storage_key=body.storage_key,
        original_name=body.original_name,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
    )
    db.add(fa)
    await db.commit()
    await db.refresh(fa)
    if body.kind in {"source_image", "source_pdf"} and not e.source_file_id:
        e.source_file_id = fa.id
        e.source_kind = body.kind
        await db.commit()
    return FileAssetOut.model_validate(fa)


@exam_router.patch("/{exam_id}/files/{file_id}", response_model=FileAssetOut)
async def rename_exam_file(
    exam_id: UUID, file_id: UUID, body: FileAssetRename,
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> FileAssetOut:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    fa = (await db.execute(select(FileAsset).where(FileAsset.id == file_id, FileAsset.exam_id == exam_id, FileAsset.deleted_at.is_(None)))).scalar_one_or_none()
    if not fa:
        raise NotFoundError("File not found.")
    fa.original_name = body.original_name
    await db.commit()
    await db.refresh(fa)
    return FileAssetOut.model_validate(fa)


@exam_router.delete("/{exam_id}/files/{file_id}", status_code=204)
async def delete_exam_file(
    exam_id: UUID, file_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    fa = (await db.execute(select(FileAsset).where(FileAsset.id == file_id, FileAsset.exam_id == exam_id, FileAsset.deleted_at.is_(None)))).scalar_one_or_none()
    if not fa:
        raise NotFoundError("File not found.")
    await db.execute(update(FileAsset).where(FileAsset.id == file_id).values(deleted_at=datetime.utcnow()))
    await db.commit()


@exam_router.get("/{exam_id}/files/{file_id}/download")
async def download_exam_file(
    exam_id: UUID, file_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
):
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    fa = (await db.execute(select(FileAsset).where(FileAsset.id == file_id, FileAsset.exam_id == exam_id, FileAsset.deleted_at.is_(None)))).scalar_one_or_none()
    if not fa:
        raise NotFoundError("File not found.")
    minio = get_minio()
    url = minio.presigned_get(fa.storage_key, expires=timedelta(minutes=5))
    # Stream the file directly with a Content-Disposition header so the filename is preserved
    from fastapi.responses import StreamingResponse
    import httpx
    async def _proxy():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk
    return StreamingResponse(
        _proxy(),
        media_type=fa.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fa.original_name}"'},
    )


@exam_router.get("/{exam_id}/pdf/questions")
async def download_questions_pdf(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
):
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    # If we have a stored PDF file, redirect there
    if e.questions_pdf_file_id:
        fa = (await db.execute(select(FileAsset).where(FileAsset.id == e.questions_pdf_file_id))).scalar_one_or_none()
        if fa:
            from app.modules.exams.pdf import render_questions_pdf
            from app.models.question import Question
            qs = (await db.execute(select(Question).where(Question.exam_id == e.id).order_by(Question.position))).scalars().all()
            pdf_bytes = render_questions_pdf(e, qs)
            from fastapi.responses import Response
            return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fa.original_name}"'})
    # Render on the fly
    from app.models.question import Question as Q
    from app.modules.exams.pdf import render_questions_pdf
    qs = (await db.execute(select(Q).where(Q.exam_id == e.id).order_by(Q.position))).scalars().all()
    if not qs:
        raise BadRequestError("Exam has no questions to render.")
    pdf_bytes = render_questions_pdf(e, qs)
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{e.title}_questions.pdf"'})


@exam_router.get("/{exam_id}/pdf/answers")
async def download_answers_pdf(
    exam_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
):
    e = (await db.execute(select(Exam).where(Exam.id == exam_id, Exam.owner_id == user.sub, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if not e:
        raise NotFoundError("Exam not found.")
    from app.models.question import Question as Q
    from app.modules.exams.pdf import render_answers_pdf
    qs = (await db.execute(select(Q).where(Q.exam_id == e.id).order_by(Q.position))).scalars().all()
    if not qs:
        raise BadRequestError("Exam has no questions to render.")
    pdf_bytes = render_answers_pdf(e, qs)
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{e.title}_answers.pdf"'})


# Run-level files
@run_router.get("/{run_id}/files", response_model=dict)
async def list_run_files(
    run_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    rows = (await db.execute(
        select(FileAsset).where(FileAsset.grading_run_id == run_id, FileAsset.deleted_at.is_(None)).order_by(FileAsset.created_at)
    )).scalars().all()
    return {"data": [FileAssetOut.model_validate(x).model_dump(mode="json") for x in rows]}


@run_router.post("/{run_id}/files", response_model=FileAssetOut, status_code=201)
async def register_run_file(
    run_id: UUID, body: FileAssetRegister, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> FileAssetOut:
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    valid = {"benchmark_pdf", "benchmark_image", "student_answer"}
    if body.kind not in valid:
        raise BadRequestError(f"Invalid kind for run file: {body.kind}")
    fa = FileAsset(
        id=uuid.uuid4(),
        owner_id=user.sub,
        grading_run_id=run_id,
        kind=body.kind,
        storage_key=body.storage_key,
        original_name=body.original_name,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
    )
    db.add(fa)
    await db.commit()
    await db.refresh(fa)
    return FileAssetOut.model_validate(fa)


@run_router.get("/{run_id}/files/{file_id}/download")
async def download_run_file(
    run_id: UUID, file_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
):
    r = (await db.execute(select(GradingRun).where(GradingRun.id == run_id, GradingRun.owner_id == user.sub, GradingRun.deleted_at.is_(None)))).scalar_one_or_none()
    if not r:
        raise NotFoundError("Grading run not found.")
    fa = (await db.execute(select(FileAsset).where(FileAsset.id == file_id, FileAsset.grading_run_id == run_id, FileAsset.deleted_at.is_(None)))).scalar_one_or_none()
    if not fa:
        raise NotFoundError("File not found.")
    minio = get_minio()
    url = minio.presigned_get(fa.storage_key, expires=timedelta(minutes=5))
    from fastapi.responses import StreamingResponse
    import httpx
    async def _proxy():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk
    return StreamingResponse(
        _proxy(),
        media_type=fa.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fa.original_name}"'},
    )
