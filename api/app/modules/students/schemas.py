"""Student schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    student_code: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    extra_columns: dict = Field(default_factory=dict)


class StudentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    student_code: Optional[str] = None
    email: Optional[EmailStr] = None
    extra_columns: Optional[dict] = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    student_code: Optional[str] = None
    email: Optional[str] = None
    extra_columns: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class ImportPreviewColumn(BaseModel):
    letter: str
    header: Optional[str]
    sample_values: list[Optional[str]] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    columns: list[ImportPreviewColumn]
    row_count: int


class ImportRequest(BaseModel):
    mapping: dict
    rows: str | list[int] = "process_all"  # 'process_all' or list of row indices


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)
