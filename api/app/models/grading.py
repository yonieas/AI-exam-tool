"""Grading models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, NUMERIC, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.user import _uuid_pk

benchmark_kind_enum = ENUM("exam_answer_key", "uploaded", name="benchmark_kind", create_type=False)
grading_run_status_enum = ENUM("draft", "grading", "needs_review", "finalized", name="grading_run_status", create_type=False)
grading_item_status_enum = ENUM("pending", "ai_processing", "ai_done", "reviewed", "final", name="grading_item_status", create_type=False)


class GradingRun(Base):
    __tablename__ = "grading_run"
    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exam.id", ondelete="RESTRICT"), nullable=False)
    benchmark_kind: Mapped[str] = mapped_column(benchmark_kind_enum, nullable=False)
    benchmark_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(grading_run_status_enum, nullable=False, default="draft")
    max_score_total: Mapped[Decimal] = mapped_column(NUMERIC(10, 2), nullable=False, default=Decimal("0"))
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class GradingItem(Base):
    __tablename__ = "grading_item"
    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    grading_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("grading_run.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("student.id", ondelete="RESTRICT"), nullable=False)
    answer_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(grading_item_status_enum, nullable=False, default="pending")
    total_score: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(10, 2), nullable=True)
    max_score_total: Mapped[Decimal] = mapped_column(NUMERIC(10, 2), nullable=False, default=Decimal("0"))
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("grading_run_id", "student_id", name="uq_grading_item_run_student"),)


class GradingItemResponse(Base):
    __tablename__ = "grading_item_response"
    id: Mapped[uuid.UUID] = _uuid_pk()
    grading_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("grading_item.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("question.id"), nullable=False)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_score: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(8, 2), nullable=True)
    max_score: Mapped[Decimal] = mapped_column(NUMERIC(8, 2), nullable=False)
    teacher_score: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(8, 2), nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(4, 3), nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    teacher_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("grading_item_id", "question_id", name="uq_response_item_question"),)
