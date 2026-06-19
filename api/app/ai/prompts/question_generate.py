"""Question generation prompts + schema."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import Exam
from app.storage.minio_client import MinioClient


def question_set_schema() -> dict:
    return {
        "$id": "QuestionSet",
        "type": "object",
        "additionalProperties": False,
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "prompt", "options", "max_score", "answer", "source_citation", "confidence"],
                    "properties": {
                        "type": {"type": "string", "enum": ["mcq", "essay"]},
                        "position": {"type": "integer", "minimum": 1},
                        "prompt": {"type": "string", "minLength": 1},
                        "options": {"type": "object"},
                        "rubric": {"type": ["object", "null"]},
                        "max_score": {"type": "number", "minimum": 0},
                        "answer": {"type": "object"},
                        "source_citation": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            }
        },
    }


async def build_generation_prompt(
    session: AsyncSession,
    exam: Exam,
    minio: MinioClient,
) -> tuple[str, list]:
    from app.models.subject import Subject
    from app.models.file_asset import FileAsset

    subject = (await session.execute(Subject.__table__.select().where(Subject.id == exam.subject_id))).first()
    subject_name = subject.name if subject else "Unknown"
    units = exam.units or []
    qmode = exam.question_type_mode
    total = exam.total_count
    mcq = exam.mcq_count or (total if qmode == "mcq" else 0)
    essay = exam.essay_count or (total if qmode == "essay" else 0)

    system = f"""You are an expert assessment author for K-12 schools.

Subject: {subject_name}
Units covered: {', '.join(units) or '(general)'}
Language: {exam.generation_config.get('language', 'en')}
Difficulty: {exam.generation_config.get('difficulty', 'medium')}

Generate {total} questions: {mcq} multiple-choice and {essay} essay.

Rules:
- Generate only what the source supports. If the source is insufficient, produce fewer questions
  rather than fabricating. Never invent facts beyond the provided source.
- For each question, include a benchmark `answer` and `source_citation` pointing to the supporting
  region of the source (or "mock" if there is no source).
- For MCQ, provide 4 choices with exactly one correct.
- For essay, provide a sample answer and a rubric (criteria + points).
- Output MUST match the supplied JSON schema. Do not include any prose outside the JSON.
"""

    content: list = []
    if exam.source_file_id:
        file_asset = (await session.execute(FileAsset.__table__.select().where(FileAsset.id == exam.source_file_id))).first()
        if file_asset:
            try:
                file_bytes = await minio.get_bytes(file_asset.storage_key)
            except Exception:
                file_bytes = b""
            if exam.source_kind == "image":
                content.append({
                    "kind": "image",
                    "data": file_bytes,
                    "mime_type": file_asset.mime_type or "image/jpeg",
                })
            else:
                # Send a text hint; the provider handles documents as text
                content.append({
                    "kind": "document",
                    "data": file_bytes,
                    "mime_type": file_asset.mime_type or "application/pdf",
                })
    return system, content
