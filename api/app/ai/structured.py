"""Structured-output validation + score clamping helpers."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def clamp_score(v: Any, max_score: Decimal | float | int) -> Decimal:
    """Clamp a score to [0, max_score]. Returns Decimal."""
    try:
        n = Decimal(str(v))
    except Exception:
        return Decimal("0")
    if n.is_nan():
        return Decimal("0")
    m = Decimal(str(max_score))
    if n < 0:
        n = Decimal("0")
    if n > m:
        n = m
    return n.quantize(Decimal("0.01"))


def clamp_confidence(v: Any) -> Decimal:
    try:
        n = Decimal(str(v))
    except Exception:
        return Decimal("0.5")
    if n < 0:
        return Decimal("0")
    if n > 1:
        return Decimal("1")
    return n.quantize(Decimal("0.001"))


def looks_like_handwriting_issue(rationale: str | None) -> bool:
    if not rationale:
        return False
    text = rationale.lower()
    keys = ["ocr", "handwriting", "illegible", "ambiguous", "unclear", "low quality"]
    return any(k in text for k in keys)
