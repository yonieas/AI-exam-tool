"""WeasyPrint-based PDF rendering for questions and answers."""
from __future__ import annotations

import io
import uuid
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import Exam
from app.models.file_asset import FileAsset
from app.models.question import Question
from app.storage.minio_client import get_minio


def _question_html(q: Question) -> str:
    choices_html = ""
    if q.type == "mcq" and isinstance(q.options, dict):
        choices = q.options.get("choices", [])
        lis = "".join(
            f"<li><strong>{chr(65 + i)}.</strong> {c.get('label', '')}</li>"
            for i, c in enumerate(choices)
        )
        choices_html = f"<ol class='choices'>{lis}</ol>"
    return f"""
    <div class="question">
      <h3>Q{q.position}. ({q.type.upper()}) — {float(q.max_score)} pts</h3>
      <p>{q.prompt}</p>
      {choices_html}
    </div>
    """


def _answer_html(q: Question) -> str:
    base = _question_html(q)
    extra = ""
    if q.type == "mcq" and isinstance(q.options, dict):
        choices = q.options.get("choices", [])
        for i, c in enumerate(choices):
            if c.get("is_correct"):
                extra = f"<p class='answer'><strong>Answer:</strong> {chr(65 + i)}. {c.get('label','')}</p>"
                break
    else:
        if q.ai_meta and isinstance(q.ai_meta, dict) and q.ai_meta.get("source_citation"):
            extra = f"<p class='answer'><strong>Source:</strong> {q.ai_meta['source_citation']}</p>"
    rubric_html = ""
    if q.rubric and isinstance(q.rubric, dict):
        criteria = q.rubric.get("criteria", [])
        if criteria:
            lis = "".join(f"<li>{c.get('label','')}: {c.get('points',0)} pts</li>" for c in criteria)
            rubric_html = f"<h4>Rubric</h4><ul>{lis}</ul>"
    return base + extra + rubric_html


def render_questions_pdf(exam: Exam, questions: Iterable[Question]) -> bytes:
    from weasyprint import HTML
    qs_html = "\n".join(_question_html(q) for q in questions)
    html = f"""
    <html>
    <head>
      <style>
        body {{ font-family: Helvetica, Arial, sans-serif; padding: 32px; color: #18181B; }}
        h1 {{ border-bottom: 2px solid #2563EB; padding-bottom: 8px; }}
        .question {{ page-break-inside: avoid; margin-bottom: 24px; }}
        ol.choices {{ margin-top: 4px; }}
        li {{ margin: 4px 0; }}
      </style>
    </head>
    <body>
      <h1>{exam.title}</h1>
      <p>Total questions: {exam.total_count}</p>
      {qs_html}
    </body>
    </html>
    """
    return HTML(string=html).write_pdf()


def render_answers_pdf(exam: Exam, questions: Iterable[Question]) -> bytes:
    from weasyprint import HTML
    qs_html = "\n".join(_answer_html(q) for q in questions)
    html = f"""
    <html>
    <head>
      <style>
        body {{ font-family: Helvetica, Arial, sans-serif; padding: 32px; color: #18181B; }}
        h1 {{ border-bottom: 2px solid #16A34A; padding-bottom: 8px; }}
        h3 {{ margin-bottom: 4px; }}
        .question {{ page-break-inside: avoid; margin-bottom: 24px; padding: 8px 0; border-bottom: 1px solid #E4E4E7; }}
        .answer {{ color: #16A34A; }}
        ol.choices {{ margin-top: 4px; }}
      </style>
    </head>
    <body>
      <h1>{exam.title} — Answer Key</h1>
      {qs_html}
    </body>
    </html>
    """
    return HTML(string=html).write_pdf()


async def _store_pdf(db: AsyncSession, exam: Exam, kind: str, filename: str, data: bytes) -> FileAsset:
    minio = get_minio()
    storage_key = f"exams/{exam.owner_id}/{exam.id}/{kind}.pdf"
    await minio.put_bytes(storage_key, data, "application/pdf")
    fa = FileAsset(
        id=uuid.uuid4(),
        owner_id=exam.owner_id,
        exam_id=exam.id,
        kind=kind,
        storage_key=storage_key,
        original_name=filename,
        mime_type="application/pdf",
        size_bytes=len(data),
        meta={},
    )
    db.add(fa)
    await db.flush()
    return fa


async def render_exam_pdfs(db: AsyncSession, exam: Exam, questions: list[Question]) -> tuple[FileAsset, FileAsset]:
    q_pdf = render_questions_pdf(exam, questions)
    a_pdf = render_answers_pdf(exam, questions)
    q_fa = await _store_pdf(db, exam, "questions_pdf", f"{exam.title}_questions.pdf", q_pdf)
    a_fa = await _store_pdf(db, exam, "answers_pdf", f"{exam.title}_answers.pdf", a_pdf)
    exam.questions_pdf_file_id = q_fa.id
    exam.answers_pdf_file_id = a_fa.id
    await db.flush()
    return q_fa, a_fa
