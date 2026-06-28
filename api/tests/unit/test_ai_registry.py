"""Unit tests for AIProvider registry and router.

These tests use lightweight dummy providers (no network) and assert:
  - routing policy resolution
  - fallback behavior on failure
  - forward-compatibility (unregistered names skipped)
  - error clarity when nothing matches
"""
from __future__ import annotations

import pytest

from app.ai.provider import AIProvider, ContentBlock, StructuredResult, Tier, Effort
from app.ai.registry import AIProviderRegistry
from app.ai.router import AIProviderRouter, RoutingPolicy
from app.ai.policies import get_preset


class _DummyProvider(AIProvider):
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls: list[tuple] = []

    def models(self) -> dict[str, str]:
        return {"cheap": self.name, "premium": self.name}

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
        self.calls.append((tier, system))
        if self.fail:
            raise RuntimeError(f"{self.name} intentionally failing")
        return StructuredResult(
            data={"from": self.name},
            tokens_in=10,
            tokens_out=5,
            cost_micro_usd=0,
            model=self.name,
            cache_hit=False,
            stop_reason="stop",
        )


class TestRegistry:
    def test_register_and_get(self):
        reg = AIProviderRegistry()
        p = _DummyProvider("a")
        reg.register("a", p)
        assert reg.has("a")
        assert reg.get("a") is p
        assert reg.list() == ["a"]

    def test_get_missing_returns_none(self):
        reg = AIProviderRegistry()
        assert reg.get("ghost") is None
        assert not reg.has("ghost")


class TestRouterSingleProvider:
    def test_routes_to_only_registered(self):
        reg = AIProviderRegistry()
        reg.register("mock", _DummyProvider("mock"))
        router = AIProviderRouter(reg, RoutingPolicy(name="single", adapters=("mock",)))
        result = router.generate_structured(
            tier="cheap", system="hi", content=[], schema={}, cache_prefix=None, effort="low"
        )
        assert result.data["from"] == "mock"

    def test_models_delegates_to_first(self):
        reg = AIProviderRegistry()
        reg.register("a", _DummyProvider("a"))
        router = AIProviderRouter(reg, RoutingPolicy(name="p", adapters=("a",)))
        assert router.models() == {"cheap": "a", "premium": "a"}


class TestRouterCascade:
    def test_uses_first_available_when_all_ok(self):
        reg = AIProviderRegistry()
        reg.register("anthropic", _DummyProvider("anthropic"))
        reg.register("minimax", _DummyProvider("minimax"))
        policy = RoutingPolicy(name="cascade", adapters=("anthropic", "minimax"))
        router = AIProviderRouter(reg, policy)
        result = router.generate_structured(
            tier="cheap", system="hi", content=[], schema={}, cache_prefix=None, effort="low"
        )
        assert result.data["from"] == "anthropic"

    def test_skips_unregistered_names_gracefully(self):
        # Simulates a policy referencing anthropic before its adapter ships
        reg = AIProviderRegistry()
        reg.register("minimax", _DummyProvider("minimax"))
        policy = RoutingPolicy(name="cascade", adapters=("anthropic", "minimax"))
        router = AIProviderRouter(reg, policy)
        result = router.generate_structured(
            tier="cheap", system="hi", content=[], schema={}, cache_prefix=None, effort="low"
        )
        assert result.data["from"] == "minimax"

    def test_fallback_on_failure(self):
        reg = AIProviderRegistry()
        reg.register("anthropic", _DummyProvider("anthropic", fail=True))
        reg.register("minimax", _DummyProvider("minimax"))
        policy = RoutingPolicy(name="cascade", adapters=("anthropic", "minimax"))
        router = AIProviderRouter(reg, policy)
        result = router.generate_structured(
            tier="cheap", system="hi", content=[], schema={}, cache_prefix=None, effort="low"
        )
        assert result.data["from"] == "minimax"

    def test_raises_when_all_fail(self):
        reg = AIProviderRegistry()
        reg.register("a", _DummyProvider("a", fail=True))
        reg.register("b", _DummyProvider("b", fail=True))
        policy = RoutingPolicy(name="cascade", adapters=("a", "b"))
        router = AIProviderRouter(reg, policy)
        with pytest.raises(RuntimeError) as exc_info:
            router.generate_structured(
                tier="cheap", system="hi", content=[], schema={}, cache_prefix=None, effort="low"
            )
        assert "All 2 provider(s)" in str(exc_info.value)

    def test_raises_when_none_registered(self):
        reg = AIProviderRegistry()
        policy = RoutingPolicy(name="empty", adapters=("ghost",))
        router = AIProviderRouter(reg, policy)
        with pytest.raises(RuntimeError) as exc_info:
            router.generate_structured(
                tier="cheap", system="hi", content=[], schema={}, cache_prefix=None, effort="low"
            )
        assert "No registered adapter" in str(exc_info.value)


class TestPolicyPresets:
    def test_cascade_preset_names(self):
        p = get_preset("cascade_with_fallback")
        assert p is not None
        assert p.adapters == ("anthropic", "minimax")

    def test_unknown_preset_returns_none(self):
        assert get_preset("nonexistent") is None