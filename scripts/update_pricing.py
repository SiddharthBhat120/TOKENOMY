"""Fetch real per-token prices from OpenRouter's public model list (no key needed).

    python scripts/update_pricing.py
Writes data/pricing.json as USD per 1M input/output tokens.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "data" / "pricing.json"


def main() -> None:
    data = httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    models = {}
    for m in data:
        p = m.get("pricing") or {}
        try:
            models[m["id"]] = {"input": float(p.get("prompt", 0)) * 1e6, "output": float(p.get("completion", 0)) * 1e6}
        except (TypeError, ValueError):
            continue
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"source": "https://openrouter.ai/api/v1/models", "fetched_at": time.strftime("%Y-%m-%d"),
                               "models": models}, indent=1), encoding="utf-8")
    for k in ("meta-llama/llama-3.2-3b-instruct", "qwen/qwen-2.5-7b-instruct", "openai/gpt-4o-mini", "openai/gpt-4o"):
        print(k, models.get(k))
    print(f"saved {len(models)} prices -> {OUT}")


if __name__ == "__main__":
    main()
