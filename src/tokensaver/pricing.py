"""Model prices (USD per 1M tokens) and cost maths.

Prices come from data/pricing.json, which `scripts/update_pricing.py` fills from
OpenRouter's public model list. Local Ollama models are priced at the public
OpenRouter rate of the same open-weights model ("price_as"), so savings are
reported at what a company would really pay for that model through an API.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Ollama model -> equivalent hosted model on OpenRouter (same open weights)
PRICE_AS: dict[str, str] = {
    "ollama/gemma3:4b": "google/gemma-3-4b-it",
    "ollama/gemma3:12b": "google/gemma-3-12b-it",
    "ollama/gemma3:27b": "google/gemma-3-27b-it",
    "ollama/llama3.2:3b": "meta-llama/llama-3.2-3b-instruct",
    "ollama/llama3.1:8b": "meta-llama/llama-3.1-8b-instruct",
    "ollama/phi4": "microsoft/phi-4",
}

# Fallback if pricing.json is missing (input, output per 1M tokens)
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "google/gemma-3-4b-it": (0.05, 0.10),
    "google/gemma-3-12b-it": (0.05, 0.15),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
}


@dataclass(frozen=True)
class Price:
    input_per_m: float
    output_per_m: float


class PriceBook:
    def __init__(self, path: Path | None = None) -> None:
        self._prices: dict[str, Price] = {k: Price(*v) for k, v in DEFAULT_PRICES.items()}
        if path and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for model, p in data.get("models", {}).items():
                self._prices[model] = Price(float(p["input"]), float(p["output"]))

    def lookup(self, model: str) -> Price | None:
        key = PRICE_AS.get(model, model)
        if key.endswith(":free"):
            key = key[: -len(":free")]
        return self._prices.get(key)

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Cost in USD of one call. Unknown models cost 0 (and are flagged in logs)."""
        price = self.lookup(model)
        if price is None:
            return 0.0
        return (prompt_tokens * price.input_per_m + completion_tokens * price.output_per_m) / 1_000_000

    def known(self, model: str) -> bool:
        return self.lookup(model) is not None
