"""Question schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuestionCreate(BaseModel):
    type: str = Field(pattern="^(mcq|essay)$")
    prompt: str = Field(min_length=1)
    options: dict = Field(default_factory=dict)
    rubric: Optional[dict] = None
    max_score: Decimal = Field(default=Decimal("1.0"), ge=0)


class QuestionUpdate(BaseModel):
    type: Optional[str] = Field(default=None, pattern="^(mcq|essay)$")
    prompt: Optional[str] = None
    options: Optional[dict] = None
    rubric: Optional[dict] = None
    max_score: Optional[Decimal] = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exam_id: UUID
    position: int
    type: str
    prompt: str
    options: dict = Field(default_factory=dict)
    rubric: Optional[dict] = None
    max_score: Decimal
    ai_meta: Optional[dict] = None
    status: str
    created_at: datetime
    updated_at: datetime
