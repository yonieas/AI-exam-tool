"""AIProvider router — implements AIProvider, delegates with fallback.

The router is itself an AIProvider (Protocol-conformant), so call sites
stay unchanged: `get_provider().generate_structured(...)` works identically
whether `get_provider()` returns a single adapter or a router.

RoutingPolicy is a named, priority-ordered list of adapter names. Names
that are not registered in the AIProviderRegistry are skipped — this is
the seam for forward-compatible policies (e.g. cascade_with_fallback can
reference 'anthropic' before that adapter ships).

Failure semantics:
  - try adapters in order
  - on Exception, log a warning and try the next
  - raise RuntimeError if all fail or none are registered
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from app.ai.provider import AIProvider, ContentBlock, StructuredResult, Tier, Effort
from app.ai.registry import AIProviderRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutingPolicy:
    """A named, priority-ordered list of adapter names.

    `adapters`: names tried in order on each request. Names not present
                in the registry are skipped silently. The first registered
                adapter is used; on its exception, the next registered
                adapter is tried.
    """
    name: str
    adapters: Sequence[str] = ()


class AIProviderRouter:
    """Implements AIProvider; delegates to underlying adapters with fallback."""

    def __init__(self, registry: AIProviderRegistry, policy: RoutingPolicy) -> None:
        self._registry = registry
        self._policy = policy
        self.name = f"router:{policy.name}"
        self._last_used_provider: Optional[str] = None

    @property
    def last_used_provider(self) -> Optional[str]:
        """Name of the provider that successfully handled the last request."""
        return self._last_used_provider

    def _first_registered(self) -> Optional[AIProvider]:
        for name in self._policy.adapters:
            p = self._registry.get(name)
            if p is not None:
                return p
        return None

    def models(self) -> dict[str, str]:
        first = self._first_registered()
        return first.models() if first is not None else {}

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
        candidates = [n for n in self._policy.adapters if self._registry.has(n)]
        if not candidates:
            raise RuntimeError(
                f"No registered adapter in policy '{self._policy.name}'. "
                f"Policy adapters: {list(self._policy.adapters)}. "
                f"Registered: {self._registry.list()}"
            )
        last_error: Optional[BaseException] = None
        for name in candidates:
            provider = self._registry.get(name)
            assert provider is not None  # filtered above
            try:
                result = provider.generate_structured(
                    tier=tier,
                    system=system,
                    content=content,
                    schema=schema,
                    cache_prefix=cache_prefix,
                    effort=effort,
                )
                self._last_used_provider = name
                return result
            except Exception as e:
                logger.warning(
                    "AI provider '%s' failed (policy '%s'): %s; trying next",
                    name, self._policy.name, e,
                )
                last_error = e
                continue
        raise RuntimeError(
            f"All {len(candidates)} provider(s) in policy '{self._policy.name}' failed"
        ) from last_error