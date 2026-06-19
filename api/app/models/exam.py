"""Exam, Question, QuestionOption models."""
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

question_type_mode_enum = ENUM("mcq", "essay", "both", name="question_type_mode", create_type=False)
exam_source_kind_enum = ENUM("none", "image", "pdf", name="exam_source_kind", create_type=False)
exam_status_enum = ENUM("draft", "in_review", "published", "closed", name="exam_status", create_type=False)
question_type_enum = ENUM("mcq", "essay", name="question_type", create_type=False)
question_status_enum = ENUM("draft", "in_review", "approved", name="question_status", create_type=False)


class Exam(Base):
    __tablename__ = "exam"
    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subject.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(exam_source_kind_enum, nullable=False, default="none")
    units: Mapped[list] = mapped_column(JSONB(), nullable=False, default=list)
    question_type_mode: Mapped[str] = mapped_column(question_type_mode_enum, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mcq_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    essay_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generation_config: Mapped[dict] = mapped_column(JSONB(), nullable=False, default=dict)
    source_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    answer_key: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    answer_key_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    questions_pdf_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    answers_pdf_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(exam_status_enum, nullable=False, default="draft")
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Question(Base):
    __tablename__ = "question"
    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exam.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(question_type_enum, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB(), nullable=False, default=dict)
    rubric: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    max_score: Mapped[Decimal] = mapped_column(NUMERIC(8, 2), nullable=False, default=Decimal("1.0"))
    ai_meta: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    status: Mapped[str] = mapped_column(question_status_enum, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("exam_id", "position", name="uq_question_exam_position"),)


class QuestionOption(Base):
    __tablename__ = "question_option"
    id: Mapped[uuid.UUID] = _uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("question.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("question_id", "position", name="uq_option_question_position"),)
