"""Upstream providers. Both speak the OpenAI chat-completions format.

- "ollama/<name>"  -> local Ollama (free, http://localhost:11434/v1), model "<name>"
- anything else    -> OpenRouter (e.g. "meta-llama/llama-3.2-3b-instruct:free")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class UpstreamError(Exception):
    def __init__(self, status: int, message: str, provider: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.provider = provider


@dataclass
class Target:
    provider: str
    url: str
    model: str
    headers: dict[str, str]


def resolve(model: str, s: Settings) -> Target:
    if model.startswith("ollama/"):
        return Target("ollama", f"{s.ollama_base_url}/chat/completions", model.split("/", 1)[1], {})
    if not s.openrouter_api_key:
        raise UpstreamError(401, "OPENROUTER_API_KEY is not set. Add it to .env, or use an 'ollama/...' model.", "openrouter")
    return Target(
        "openrouter",
        f"{s.openrouter_base_url}/chat/completions",
        model,
        {
            "Authorization": f"Bearer {s.openrouter_api_key}",
            "HTTP-Referer": "https://github.com/SiddharthBhat120/TOKENOMY",
            "X-Title": "Tokenomy",
        },
    )


async def chat(client: httpx.AsyncClient, model: str, body: dict[str, Any], s: Settings) -> dict:
    target = resolve(model, s)
    payload = {**body, "model": target.model, "stream": False}
    try:
        r = await client.post(target.url, json=payload, headers=target.headers, timeout=s.upstream_timeout)
    except httpx.TimeoutException as e:
        raise UpstreamError(504, f"{target.provider} timed out", target.provider) from e
    except httpx.ConnectError as e:
        hint = " Is Ollama running? (ollama serve)" if target.provider == "ollama" else ""
        raise UpstreamError(502, f"Cannot reach {target.provider}.{hint}", target.provider) from e
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {})
            msg = msg.get("message", str(msg)) if isinstance(msg, dict) else str(msg)
        except Exception:
            msg = r.text[:300]
        status = r.status_code if r.status_code in (400, 401, 402, 403, 404, 408, 413, 422, 429) else 502
        raise UpstreamError(status, f"{target.provider}: {msg}", target.provider)
    data = r.json()
    data["model"] = model  # report the Tokenomy model id back to the client
    return data
