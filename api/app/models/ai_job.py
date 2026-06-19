"""AI Job model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.user import _uuid_pk

ai_job_type_enum = ENUM("question_generation", "grading", name="ai_job_type", create_type=False)
ai_job_status_enum = ENUM("queued", "processing", "done", "failed", name="ai_job_status", create_type=False)
ai_provider_enum = ENUM("minimax", "mock", name="ai_provider", create_type=False)


class AIJob(Base):
    __tablename__ = "ai_job"
    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(ai_job_type_enum, nullable=False)
    job_status: Mapped[str] = mapped_column(ai_job_status_enum, nullable=False, default="queued")
    exam_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    grading_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    grading_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    input_payload: Mapped[dict] = mapped_column(JSONB(), nullable=False, default=dict)
    output_payload: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd_micro: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ai_provider: Mapped[str] = mapped_column(ai_provider_enum, nullable=False, default="minimax")
    model: Mapped[str] = mapped_column(Text, nullable=False, default="MiniMax-M2.7")
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="uq_ai_job_idem"),)
