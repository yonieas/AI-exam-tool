"""Preset routing policies for the AIProvider router.

A preset is a named, ordered list of adapter names. Names that aren't
registered are skipped by the router — that's the forward-compatibility
mechanism: a policy can reference 'anthropic' before that adapter is
implemented; when it's added, the cascade activates without code change.

`single_provider` is the default and matches the previous single-adapter
behavior: it carries a single name supplied at construction time (the
factory fills it in from AI_PROVIDER).

`cascade_with_fallback` puts Anthropic first (when available) and falls
back to MiniMax. When MiniMax is the only registered adapter (current
state), the router uses it.
"""
from __future__ import annotations

from app.ai.router import RoutingPolicy


PRESETS: dict[str, RoutingPolicy] = {
    "cascade_with_fallback": RoutingPolicy(
        name="cascade_with_fallback",
        adapters=("anthropic", "minimax"),
    ),
}


def get_preset(name: str) -> RoutingPolicy | None:
    return PRESETS.get(name)