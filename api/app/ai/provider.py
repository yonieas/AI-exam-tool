"""AIProvider port and base types (ADR-009)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

Tier = Literal["cheap", "premium"]
Effort = Literal["low", "medium", "high"]


@dataclass
class ContentBlock:
    kind: Literal["text", "image", "document"]
    data: bytes | str
    mime_type: str | None = None


@dataclass
class StructuredResult:
    data: dict
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int
    model: str
    cache_hit: bool
    stop_reason: str


class AIProvider(Protocol):
    name: str

    def models(self) -> dict[str, str]: ...

    def generate_structured(
        self,
        *,
        tier: Tier,
        system: str,
        content: list[ContentBlock],
        schema: dict,
        cache_prefix: str | None,
        effort: Effort,
    ) -> StructuredResult: ...
