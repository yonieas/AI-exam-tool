"""MiniMax (default) AI provider — OpenAI-compatible API."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from app.ai.provider import AIProvider, ContentBlock, StructuredResult, Tier, Effort
from app.ai.structured import clamp_confidence, clamp_score
from app.config import get_settings


class MiniMaxProvider(AIProvider):
    name = "minimax"

    def __init__(self) -> None:
        s = get_settings()
        self._client = OpenAI(api_key=s.minimax_api_key or "sk-mock", base_url=s.minimax_base_url)
        self._model = s.minimax_model
        self._cheap_model = s.minimax_cheap_model

    def models(self) -> dict[str, str]:
        return {"cheap": self._cheap_model, "premium": self._model}

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
        model = self._model if tier == "premium" else self._cheap_model

        # Build messages: a stable cache prefix goes first as a system message
        prefix = ""
        if cache_prefix:
            prefix = f"[CACHE-STABLE]\n{cache_prefix}\n[END CACHE-STABLE]\n"
        full_system = prefix + system

        user_content: list[dict[str, Any]] = []
        for block in content:
            if block.kind == "text":
                user_content.append({"type": "text", "text": str(block.data)})
            elif block.kind == "image":
                import base64
                b64 = base64.b64encode(block.data if isinstance(block.data, bytes) else block.data.encode()).decode()
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{block.mime_type or 'image/jpeg'};base64,{b64}"},
                })
            elif block.kind == "document":
                # For PDFs and other docs, send as text (in production, the API would support file parts)
                user_content.append({"type": "text", "text": f"[Document bytes omitted: {len(block.data) if isinstance(block.data, (bytes, bytearray)) else 'n/a'}]"})

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_content if user_content else "Proceed."},
        ]

        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {"name": schema.get("$id", "Response"), "schema": schema, "strict": True}},
            temperature=0.2,
        )
        choice = response.choices[0]
        raw = choice.message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Provider returned non-JSON: {e}; raw={raw[:200]}")

        usage = response.usage
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0

        return StructuredResult(
            data=data,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_micro_usd=0,
            model=model,
            cache_hit=False,
            stop_reason=getattr(choice, "finish_reason", "stop") or "stop",
        )
