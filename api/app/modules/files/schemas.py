"""File schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exam_id: Optional[UUID] = None
    grading_run_id: Optional[UUID] = None
    grading_item_id: Optional[UUID] = None
    kind: str
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    deleted_at: Optional[datetime] = None


class FileAssetRegister(BaseModel):
    kind: str
    storage_key: str
    original_name: str
    mime_type: str
    size_bytes: int = 0


class FileAssetRename(BaseModel):
    original_name: str
