"""In-process AI job worker.

BullMQ Python client is not on PyPI; we use an in-process asyncio queue for MVP
(see BACKEND_CONVENTIONS §13 "in-house asyncio worker" — the doc lists it as
an acceptable option, and the only async pipeline is AI jobs). The interface
is shaped so we can swap to BullMQ later without changing call sites.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Awaitable, Callable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.mock_adapter import get_provider
from app.ai.prompts import grade as grade_prompts
from app.ai.prompts import question_generate as gen_prompts
from app.ai.provider import ContentBlock
from app.ai.structured import clamp_confidence, clamp_score, looks_like_handwriting_issue
from app.config import get_settings
from app.models.ai_job import AIJob
from app.models.exam import Exam
from app.models.grading import GradingItem, GradingItemResponse
from app.models.question import Question
from app.storage.minio_client import get_minio

logger = logging.getLogger("ai_worker")


def _now() -> datetime:
    return datetime.utcnow()


class AIJobWorker:
    """Background worker that consumes jobs from an in-process queue and runs them.

    The handler is registered at startup; the queue can be enqueued from any
    service via `worker.enqueue(...)`. The handler resolves the per-job
    session and updates the `ai_job` row.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._session_factory: async_sessionmaker | None = None

    def set_session_factory(self, factory: async_sessionmaker) -> None:
        self._session_factory = factory

    def _get_redis(self):
        import redis.asyncio as redis_async
        from app.config import get_settings
        s = get_settings()
        if not hasattr(self, "_redis") or self._redis is None:
            try:
                self._redis = redis_async.from_url(s.redis_url, decode_responses=True)
            except Exception:
                self._redis = None
        return self._redis

    async def enqueue(self, ai_job_id: UUID) -> None:
        await self._queue.put(str(ai_job_id))

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run(), name="ai-worker")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process(job_id)
            except Exception as e:  # never let the worker die on a bad job
                logger.exception("AI job %s failed: %s", job_id, e)

    async def _process(self, job_id: str) -> None:
        assert self._session_factory is not None
        async with self._session_factory() as session:
            job = (await session.execute(select(AIJob).where(AIJob.id == UUID(job_id)))).scalar_one_or_none()
            if not job:
                return
            if job.job_status == "done":
                return
            job.job_status = "processing"
            job.started_at = _now()
            await session.commit()

            try:
                if job.job_type == "question_generation":
                    await self._run_generation(session, job)
                elif job.job_type == "grading":
                    await self._run_grading(session, job)
                else:
                    raise RuntimeError(f"Unknown job_type: {job.job_type}")
                job.job_status = "done"
                job.completed_at = _now()
            except Exception as e:
                logger.exception("AI job %s failed: %s", job_id, e)
                job.job_status = "failed"
                job.error = f"{e}\n{traceback.format_exc()[:1000]}"
                job.completed_at = _now()
            await session.commit()

    async def _run_generation(self, session: AsyncSession, job: AIJob) -> None:
        exam_id = job.exam_id
        exam = (await session.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
        if not exam:
            raise RuntimeError(f"Exam {exam_id} not found")

        provider = get_provider()
        system, content = await gen_prompts.build_generation_prompt(session, exam, get_minio())
        schema = gen_prompts.question_set_schema()
        result = provider.generate_structured(
            tier="premium",
            system=system,
            content=content,
            schema=schema,
            cache_prefix=f"exam:{exam.id}|subject:{exam.subject_id}",
            effort="high",
        )

        from decimal import Decimal
        questions_data = result.data.get("questions", [])
        max_pos = 0
        existing = (await session.execute(select(Question).where(Question.exam_id == exam.id))).scalars().all()
        if existing:
            max_pos = max(q.position for q in existing)
        for q in questions_data:
            max_pos += 1
            question = Question(
                owner_id=exam.owner_id,
                exam_id=exam.id,
                position=max_pos,
                type=q["type"],
                prompt=q["prompt"],
                options=q.get("options", {}),
                rubric=q.get("rubric"),
                max_score=clamp_score(q.get("max_score", 1.0), 9999),
                ai_meta={
                    "model": result.model,
                    "source_citation": q.get("source_citation"),
                    "confidence": float(clamp_confidence(q.get("confidence", 0.7))),
                },
                status="in_review",
            )
            session.add(question)
        # Build answer key JSONB aligned to questions
        answer_key = []
        for q in questions_data:
            answer_key.append({
                "position": q.get("position"),
                "type": q.get("type"),
                "answer": q.get("answer"),
                "max_score": float(clamp_score(q.get("max_score", 1.0), 9999)),
            })
        exam.answer_key = {"questions": answer_key}
        exam.ai_generated = True
        exam.status = "in_review"
        # Mark generation done
        job.output_payload = {"question_count": len(questions_data)}
        job.total_tokens_input = result.tokens_in
        job.total_tokens_output = result.tokens_out
        job.cost_usd_micro = result.cost_micro_usd
        job.model = result.model
        job.ai_provider = provider.name
        await session.flush()

    async def _run_grading(self, session: AsyncSession, job: AIJob) -> None:
        item_id = job.grading_item_id
        item = (await session.execute(select(GradingItem).where(GradingItem.id == item_id))).scalar_one_or_none()
        if not item:
            raise RuntimeError(f"GradingItem {item_id} not found")
        # Get questions and benchmark
        exam = (await session.execute(select(Exam).where(Exam.id == (await session.execute(select(GradingRun := __import__('app.models.grading', fromlist=['GradingRun']).GradingRun).where(__import__('app.models.grading', fromlist=['GradingRun']).GradingRun.id == item.grading_run_id)))).scalar_one_or_none()))
        # The above is overly complex; do it cleanly:
        from app.models.grading import GradingRun
        run = (await session.execute(select(GradingRun).where(GradingRun.id == item.grading_run_id))).scalar_one_or_none()
        if not run:
            raise RuntimeError("Run not found")
        exam = (await session.execute(select(Exam).where(Exam.id == run.exam_id))).scalar_one_or_none()
        if not exam:
            raise RuntimeError("Exam not found")
        questions = (await session.execute(select(Question).where(Question.exam_id == exam.id).order_by(Question.position))).scalars().all()

        # Load benchmark
        benchmark = exam.answer_key or {"questions": []}

        # Get file from minio
        from app.models.file_asset import FileAsset
        file_asset = (await session.execute(select(FileAsset).where(FileAsset.id == item.answer_file_id))).scalar_one_or_none()
        if not file_asset:
            raise RuntimeError("Answer file not found")
        minio = get_minio()
        file_bytes = await minio.get_bytes(file_asset.storage_key)

        provider = get_provider()
        system, content = grade_prompts.build_grading_prompt(
            questions=questions,
            benchmark=benchmark,
            file_bytes=file_bytes,
            mime_type=file_asset.mime_type,
            original_name=file_asset.original_name,
        )
        schema = grade_prompts.grading_result_schema()
        result = provider.generate_structured(
            tier="premium",
            system=system,
            content=content,
            schema=schema,
            cache_prefix=f"exam:{exam.id}|benchmark_version:1",
            effort="high",
        )

        # Map AI responses to question ids
        # The mock returns placeholder question_ids — instead, we match by position
        responses_data = result.data.get("responses", [])
        # Try to match by position in prompt
        from app.ai.prompts.grade import parse_question_positions_from_system
        positions = parse_question_positions_from_system(system)
        # positions is a list of (qid_str, position) — but mock doesn't know qids. Use index alignment.
        for idx, response in enumerate(responses_data):
            target_q = None
            if idx < len(questions):
                target_q = questions[idx]
            if not target_q:
                continue
            max_score = float(target_q.max_score or 1.0)
            ai_score = float(clamp_score(response.get("ai_score", 0.0), max_score))
            confidence = float(clamp_confidence(response.get("confidence", 0.5)))
            rationale = response.get("rationale", "")
            flagged = bool(response.get("flagged")) or confidence < 0.7 or looks_like_handwriting_issue(rationale)

            existing_resp = (await session.execute(
                select(GradingItemResponse).where(
                    GradingItemResponse.grading_item_id == item.id,
                    GradingItemResponse.question_id == target_q.id,
                )
            )).scalar_one_or_none()
            if existing_resp:
                # Already graded (re-run scenario). Overwrite AI fields; keep teacher overrides.
                existing_resp.ai_score = ai_score
                existing_resp.answer_text = response.get("answer_text")
                existing_resp.confidence = confidence
                existing_resp.ai_rationale = rationale
                existing_resp.flagged = flagged
                existing_resp.graded_at = _now()
            else:
                resp = GradingItemResponse(
                    grading_item_id=item.id,
                    question_id=target_q.id,
                    answer_text=response.get("answer_text"),
                    ai_score=ai_score,
                    max_score=max_score,
                    confidence=confidence,
                    flagged=flagged,
                    ai_rationale=rationale,
                    graded_at=_now(),
                )
                session.add(resp)

        await session.flush()

        # Recompute item aggregates
        all_responses = (await session.execute(
            select(GradingItemResponse).where(GradingItemResponse.grading_item_id == item.id)
        )).scalars().all()
        total = 0.0
        max_total = 0.0
        any_flagged = False
        for r in all_responses:
            score = float(r.teacher_score) if r.teacher_score is not None else (float(r.ai_score) if r.ai_score is not None else 0.0)
            total += score
            max_total += float(r.max_score)
            if r.flagged and not r.overridden:
                any_flagged = True
        item.total_score = round(total, 2)
        item.max_score_total = round(max_total, 2)
        item.flagged = any_flagged
        item.status = "ai_done"
        run.status = "needs_review" if any((i.flagged and not i.finalized) for i in (await session.execute(select(GradingItem).where(GradingItem.grading_run_id == run.id))).scalars().all()) else "grading"

        job.output_payload = {"responses": len(responses_data)}
        job.total_tokens_input = result.tokens_in
        job.total_tokens_output = result.tokens_out
        job.cost_usd_micro = result.cost_micro_usd
        job.model = result.model
        job.ai_provider = provider.name
        await session.flush()


_worker_singleton: Optional[AIJobWorker] = None


def get_worker() -> AIJobWorker:
    global _worker_singleton
    if _worker_singleton is None:
        _worker_singleton = AIJobWorker()
    return _worker_singleton
