"""Class schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    grade_level: Optional[int] = None
    subject_ids: list[UUID] = Field(default_factory=list)


class ClassUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    grade_level: Optional[int] = None


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    grade_level: Optional[int] = None
    subject_ids: list[UUID] = []
    student_count: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class ClassSubjectAssign(BaseModel):
    subject_ids: list[UUID] = Field(default_factory=list)


class ClassEnrollmentCreate(BaseModel):
    student_id: UUID
