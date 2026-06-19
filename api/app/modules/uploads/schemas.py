"""Upload schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class PresignRequest(BaseModel):
    kind: str
    exam_id: Optional[UUID] = None
    grading_run_id: Optional[UUID] = None
    grading_item_id: Optional[UUID] = None
    filename: str = Field(min_length=1, max_length=300)
    mime_type: str = Field(min_length=1, max_length=200)
    size_bytes: int = 0


class PresignResponse(BaseModel):
    upload_url: str
    storage_key: str
    method: str = "PUT"
    headers: dict
