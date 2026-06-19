"""AI job polling route."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser
from app.errors import NotFoundError
from app.models.ai_job import AIJob

router = APIRouter(prefix="/ai-jobs", tags=["ai-jobs"])


@router.get("/{job_id}", response_model=dict)
async def get_job(
    job_id: UUID, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    j = (await db.execute(select(AIJob).where(AIJob.id == job_id, AIJob.owner_id == user.sub))).scalar_one_or_none()
    if not j:
        raise NotFoundError("AI job not found.")
    return {
        "id": str(j.id),
        "job_type": j.job_type,
        "job_status": j.job_status,
        "exam_id": str(j.exam_id) if j.exam_id else None,
        "grading_run_id": str(j.grading_run_id) if j.grading_run_id else None,
        "grading_item_id": str(j.grading_item_id) if j.grading_item_id else None,
        "queued_at": j.queued_at.isoformat() if j.queued_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "error": j.error,
        "model": j.model,
        "ai_provider": j.ai_provider,
        "total_tokens_input": j.total_tokens_input,
        "total_tokens_output": j.total_tokens_output,
        "cost_usd_micro": j.cost_usd_micro,
        "poll_url": f"/api/v1/ai-jobs/{j.id}",
        "output_payload": j.output_payload,
    }
