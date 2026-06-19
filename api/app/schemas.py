"""Cross-module Pydantic schemas shared across modules."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TimestampedSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime | None = None


class SoftDeletedSchema(BaseModel):
    deleted_at: datetime | None = None


# Enums used across modules
class QuestionTypeMode(str):
    MCQ = "mcq"
    ESSAY = "essay"
    BOTH = "both"


class QuestionType(str):
    MCQ = "mcq"
    ESSAY = "essay"


class QuestionStatus(str):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"


class ExamStatus(str):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    CLOSED = "closed"


class ExamSourceKind(str):
    NONE = "none"
    IMAGE = "image"
    PDF = "pdf"


class BenchmarkKind(str):
    EXAM_ANSWER_KEY = "exam_answer_key"
    UPLOADED = "uploaded"


class GradingRunStatus(str):
    DRAFT = "draft"
    GRADING = "grading"
    NEEDS_REVIEW = "needs_review"
    FINALIZED = "finalized"


class GradingItemStatus(str):
    PENDING = "pending"
    AI_PROCESSING = "ai_processing"
    AI_DONE = "ai_done"
    REVIEWED = "reviewed"
    FINAL = "final"


class FileAssetKind(str):
    SOURCE_IMAGE = "source_image"
    SOURCE_PDF = "source_pdf"
    QUESTIONS_PDF = "questions_pdf"
    ANSWERS_PDF = "answers_pdf"
    BENCHMARK_PDF = "benchmark_pdf"
    BENCHMARK_IMAGE = "benchmark_image"
    STUDENT_ANSWER = "student_answer"


class AIJobType(str):
    QUESTION_GENERATION = "question_generation"
    GRADING = "grading"


class AIJobStatus(str):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class AIProviderName(str):
    MINIMAX = "minimax"


# Cursor pagination
class PageMeta(BaseModel):
    next_cursor: str | None = None
    limit: int = 50
    has_more: bool = False


class PaginatedList(BaseModel):
    data: list[Any]
    page: PageMeta


def make_cursor(item_id: UUID, /, *, before: bool = False) -> str:
    """Create an opaque cursor from an item id."""
    import base64
    payload = f"{item_id}{'B' if before else ''}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def parse_cursor(cursor: str) -> tuple[UUID, bool]:
    """Parse a cursor back to (last_id, before_flag)."""
    import base64
    payload = base64.urlsafe_b64decode(cursor.encode()).decode()
    before = payload.endswith("B")
    if before:
        payload = payload[:-1]
    return UUID(payload), before
