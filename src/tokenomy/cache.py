"""Exact-match cache.

Key = SHA-256 of (model, normalised messages, sampling params that change the answer).
Only low-temperature requests are cached: at high temperature the caller is asking
for variety, so replaying one stored answer would break their expectation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# request fields that change the answer and therefore belong in the key
KEY_PARAMS = ("temperature", "top_p", "max_tokens", "stop", "response_format", "tools", "tool_choice", "seed")


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim whitespace and lowercase roles so trivially-different requests share a key."""
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            content = " ".join(content.split())
        out.append({"role": str(m.get("role", "")).lower(), "content": content})
    return out


def cache_key(model: str, body: dict[str, Any]) -> str:
    payload = {
        "model": model,
        "messages": normalize_messages(body.get("messages", [])),
        **{p: body.get(p) for p in KEY_PARAMS if body.get(p) is not None},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_cacheable(body: dict[str, Any], max_temperature: float) -> bool:
    if body.get("n", 1) != 1:
        return False
    temperature = body.get("temperature", 1.0)  # OpenAI default is 1.0
    return temperature is not None and float(temperature) <= max_temperature
