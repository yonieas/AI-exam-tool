"""Mock AI adapter for local development — returns deterministic structured outputs."""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.ai.provider import AIProvider, ContentBlock, StructuredResult, Tier, Effort
from app.ai.structured import clamp_confidence, clamp_score


MOCK_MODEL = "mock-minimax-m2.7"


class MockProvider(AIProvider):
    name = "mock"

    def models(self) -> dict[str, str]:
        return {"cheap": MOCK_MODEL, "premium": MOCK_MODEL}

    def generate_structured(
        self,
        *,
        tier: Tier,
        system: str,
        content: list[ContentBlock],
        schema: dict,
        cache_prefix: str | None,
        effort: Effort,
    ) -> StructuredResult:
        # Heuristic: detect which schema the caller is asking for by schema id/title
        schema_id = (schema.get("$id") or schema.get("title") or "").lower()
        if "questionset" in schema_id or "question" in schema_id:
            return self._questions(system, content, schema)
        if "gradingresult" in schema_id or "responses" in schema_id:
            return self._grading(system, content, schema)
        # Generic: wrap an echo so callers still get a structured response
        return StructuredResult(
            data={"echo": "unknown_schema", "schema_keys": list(schema.keys())},
            tokens_in=10,
            tokens_out=5,
            cost_micro_usd=0,
            model=MOCK_MODEL,
            cache_hit=False,
            stop_reason="end_turn",
        )

    def _questions(self, system: str, content: list[ContentBlock], schema: dict) -> StructuredResult:
        # Parse requested counts from system prompt when present.
        total = 5
        mcq_n = 0
        essay_n = 0
        try:
            import re
            m_total = re.search(r"Generate\s+(\d+)", system)
            m_mcq = re.search(r"(\d+)\s+multiple-choice", system)
            m_essay = re.search(r"and\s+(\d+)\s+essay", system)
            if m_total:
                total = int(m_total.group(1))
            if m_mcq:
                mcq_n = int(m_mcq.group(1))
            if m_essay:
                essay_n = int(m_essay.group(1))
            # If only "total" is set and counts are missing, split evenly
            if total and mcq_n == 0 and essay_n == 0:
                mcq_n = total
                essay_n = 0
        except Exception:
            pass
        # Cap to total
        if mcq_n + essay_n > total:
            essay_n = max(0, total - mcq_n)

        questions: list[dict] = []
        pos = 1
        for i in range(mcq_n):
            choices = [
                {"label": f"Choice A for Q{pos}", "is_correct": True},
                {"label": f"Choice B for Q{pos}", "is_correct": False},
                {"label": f"Choice C for Q{pos}", "is_correct": False},
                {"label": f"Choice D for Q{pos}", "is_correct": False},
            ]
            questions.append({
                "type": "mcq",
                "position": pos,
                "prompt": f"(Mock) MCQ question {pos} about the requested subject.",
                "options": {"choices": choices},
                "rubric": None,
                "max_score": 1.0,
                "answer": {"correct_choice_index": 0},
                "source_citation": "mock",
                "confidence": 0.9,
            })
            pos += 1
        for i in range(essay_n):
            questions.append({
                "type": "essay",
                "position": pos,
                "prompt": f"(Mock) Essay question {pos}: explain a key concept in 3-5 sentences.",
                "options": {},
                "rubric": {"criteria": [{"label": "Correctness", "points": 1.0}, {"label": "Clarity", "points": 1.0}]},
                "max_score": 5.0,
                "answer": {"sample": "(Mock) A model answer would go here, covering the main idea and giving an example."},
                "source_citation": "mock",
                "confidence": 0.85,
            })
            pos += 1

        return StructuredResult(
            data={"questions": questions},
            tokens_in=200,
            tokens_out=400,
            cost_micro_usd=0,
            model=MOCK_MODEL,
            cache_hit=False,
            stop_reason="end_turn",
        )

    def _grading(self, system: str, content: list[ContentBlock], schema: dict) -> StructuredResult:
        # Find referenced questions in the system prompt
        import re
        # The system prompt contains question blocks: "(Q1) ... max=N"
        # and an answer key block. We do a best-effort parse.
        responses: list[dict] = []
        # Simple regex over the system to count questions
        q_matches = re.findall(r"\(Q(\d+)\)[^|]*\|\s*max=(\d+(?:\.\d+)?)", system)
        confidences = [0.92, 0.6, 0.95, 0.55, 0.88, 0.7]  # make some items flagged
        idx = 0
        for qid, max_score in q_matches:
            conf = confidences[idx % len(confidences)]
            maxs = float(max_score)
            # Award something proportional to confidence, with full marks for high confidence, partial for low
            awarded = round(maxs * conf, 2) if conf > 0.6 else round(maxs * 0.4, 2)
            responses.append({
                "question_id": str(uuid.uuid4()),  # placeholders; the worker replaces with real ids
                "answer_text": f"(Mock) extracted answer for Q{qid}",
                "ai_score": awarded,
                "max_score": maxs,
                "confidence": conf,
                "flagged": conf < 0.7,
                "rationale": "Mock rationale: partial match" if conf < 0.85 else "Mock rationale: clean match",
            })
            idx += 1
        if not responses:
            # Fallback: produce one response
            responses.append({
                "question_id": str(uuid.uuid4()),
                "answer_text": "(Mock) no questions detected; placeholder response.",
                "ai_score": 0.5,
                "max_score": 1.0,
                "confidence": 0.5,
                "flagged": True,
                "rationale": "Mock fallback response.",
            })
        return StructuredResult(
            data={"responses": responses, "overall_confidence": 0.7},
            tokens_in=300,
            tokens_out=200,
            cost_micro_usd=0,
            model=MOCK_MODEL,
            cache_hit=False,
            stop_reason="end_turn",
        )


def _build_provider() -> AIProvider:
    """Construct the configured adapter (or router of adapters).

    The router is itself an AIProvider, so call sites are unchanged.
    """
    from app.config import get_settings
    from app.ai.policies import get_preset
    from app.ai.registry import AIProviderRegistry
    from app.ai.router import AIProviderRouter, RoutingPolicy

    s = get_settings()
    registry = AIProviderRegistry()
    if s.ai_provider == "mock":
        registry.register("mock", MockProvider())
    if s.ai_provider == "minimax":
        from app.ai.minimax_adapter import MiniMaxProvider
        registry.register("minimax", MiniMaxProvider())
    if s.ai_provider not in ("mock", "minimax"):
        # Unknown value — keep current behavior: no adapters registered → clear error
        pass

    preset = get_preset(s.ai_provider_policy)
    if preset is not None:
        policy = preset
    else:
        # single_provider — the configured AI_PROVIDER is the only adapter.
        # Forward-compat: if AI_PROVIDER=anthropic and no preset uses it, the
        # router will raise a clear error at first call.
        policy = RoutingPolicy(name="single_provider", adapters=(s.ai_provider,))

    return AIProviderRouter(registry, policy)


_PROVIDER_SINGLETON: AIProvider | None = None


def get_provider() -> AIProvider:
    """Returns a process-singleton AIProvider (router or single adapter)."""
    global _PROVIDER_SINGLETON
    if _PROVIDER_SINGLETON is None:
        _PROVIDER_SINGLETON = _build_provider()
    return _PROVIDER_SINGLETON


def reset_provider_singleton() -> None:
    """Test helper: clear the cached provider so a new build runs."""
    global _PROVIDER_SINGLETON
    _PROVIDER_SINGLETON = None
