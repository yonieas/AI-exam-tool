"""Grading schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GradingRunCreate(BaseModel):
    exam_id: UUID
    title: str = Field(min_length=1, max_length=300)
    benchmark_kind: str = Field(pattern="^(exam_answer_key|uploaded)$")
    benchmark_file_id: Optional[UUID] = None
    student_ids: list[UUID] = Field(default_factory=list)


class GradingRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exam_id: UUID
    title: str
    benchmark_kind: str
    benchmark_file_id: Optional[UUID] = None
    status: str
    max_score_total: Decimal
    finalized_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    flagged_count: int = 0
    finalized_count: int = 0


class GradingItemCreate(BaseModel):
    student_id: UUID
    file_asset_id: UUID


class GradingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grading_run_id: UUID
    student_id: UUID
    student_name: Optional[str] = None
    answer_file_id: UUID
    status: str
    total_score: Optional[Decimal] = None
    max_score_total: Decimal
    flagged: bool
    finalized: bool
    created_at: datetime
    updated_at: datetime


class GradingResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grading_item_id: UUID
    question_id: UUID
    question_position: Optional[int] = None
    question_prompt: Optional[str] = None
    question_max_score: Optional[Decimal] = None
    answer_text: Optional[str] = None
    ai_score: Optional[Decimal] = None
    max_score: Decimal
    teacher_score: Optional[Decimal] = None
    confidence: Optional[Decimal] = None
    flagged: bool
    ai_rationale: Optional[str] = None
    teacher_rationale: Optional[str] = None
    overridden: bool
    graded_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None


class GradingItemDetail(GradingItemOut):
    responses: list[GradingResponseOut] = Field(default_factory=list)


class GradingOverride(BaseModel):
    teacher_score: Decimal = Field(ge=0)
    teacher_rationale: Optional[str] = None


class GradingFinalizeResponse(BaseModel):
    id: UUID
    status: str
    finalized_at: Optional[datetime] = None
    summary: dict
