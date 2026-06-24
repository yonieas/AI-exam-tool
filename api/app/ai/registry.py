"""AIProvider registry — named adapter container (ADR-009).

Holds concrete AIProvider implementations keyed by name. The router resolves
a policy into an ordered list of names, then asks the registry for the
adapters. Providers that aren't registered are skipped (forward-compat: a
policy can reference 'anthropic' before the adapter ships).

ponytail: single-tenant MVP — no per-owner provider override. The registry
is a process-global singleton. Upgrade path: per-tenant provider routing
keyed by owner_id (see AI_PROVIDER_RESEARCH.md §4.4 open items).
"""
from __future__ import annotations

from typing import Optional

from app.ai.provider import AIProvider


class AIProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def register(self, name: str, provider: AIProvider) -> None:
        self._providers[name] = provider

    def has(self, name: str) -> bool:
        return name in self._providers

    def get(self, name: str) -> Optional[AIProvider]:
        return self._providers.get(name)

    def list(self) -> list[str]:
        return list(self._providers.keys())