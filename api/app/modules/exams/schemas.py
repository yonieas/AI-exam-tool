"""Exam schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExamSource(BaseModel):
    kind: str  # 'image' | 'pdf' | 'none'
    file_asset_id: Optional[UUID] = None


class ExamCreate(BaseModel):
    subject_id: UUID
    title: str = Field(min_length=1, max_length=300)
    units: list[str] = Field(default_factory=list)
    question_type_mode: str = Field(pattern="^(mcq|essay|both)$")
    total_count: int = Field(ge=1, le=200)
    mcq_count: Optional[int] = Field(default=None, ge=0)
    essay_count: Optional[int] = Field(default=None, ge=0)
    generation_config: dict = Field(default_factory=dict)
    source: Optional[ExamSource] = None

    @model_validator(mode="after")
    def _check_counts(self):
        if self.question_type_mode == "mcq":
            if self.mcq_count not in (None, self.total_count):
                raise ValueError("mcq_count must equal total_count when mode=mcq")
        elif self.question_type_mode == "essay":
            if self.essay_count not in (None, self.total_count):
                raise ValueError("essay_count must equal total_count when mode=essay")
        elif self.question_type_mode == "both":
            if self.mcq_count is None or self.essay_count is None:
                raise ValueError("mcq_count and essay_count are required when mode=both")
            if self.mcq_count + self.essay_count != self.total_count:
                raise ValueError("mcq_count + essay_count must equal total_count")
        return self


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    units: Optional[list[str]] = None
    total_count: Optional[int] = Field(default=None, ge=1)
    mcq_count: Optional[int] = None
    essay_count: Optional[int] = None
    generation_config: Optional[dict] = None


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_id: UUID
    title: str
    source_kind: str = "none"
    units: list[str] = Field(default_factory=list)
    question_type_mode: str
    total_count: int
    mcq_count: Optional[int] = None
    essay_count: Optional[int] = None
    generation_config: dict = Field(default_factory=dict)
    source_file_id: Optional[UUID] = None
    answer_key: Optional[dict] = None
    questions_pdf_file_id: Optional[UUID] = None
    answers_pdf_file_id: Optional[UUID] = None
    status: str = "draft"
    ai_generated: bool = False
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    question_count: int = 0
