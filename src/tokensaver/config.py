"""Settings, loaded once from environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _str(name: str, default: str) -> str:
    # strip inline comments like "classifier   # rules | classifier"
    return os.getenv(name, default).split("#", 1)[0].strip() or default


@dataclass
class Settings:
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "").strip())
    openrouter_base_url: str = field(default_factory=lambda: _str("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    ollama_base_url: str = field(default_factory=lambda: _str("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    upstream_timeout: float = field(default_factory=lambda: float(_str("UPSTREAM_TIMEOUT", "120")))

    cache_ttl_seconds: int = field(default_factory=lambda: int(_str("CACHE_TTL_SECONDS", "86400")))
    cache_max_temperature: float = field(default_factory=lambda: float(_str("CACHE_MAX_TEMPERATURE", "0.3")))
    semantic_enabled: bool = field(default_factory=lambda: _bool("SEMANTIC_CACHE_ENABLED", True))
    semantic_threshold: float = field(default_factory=lambda: float(_str("SEMANTIC_THRESHOLD", "0.85")))
    semantic_max_messages: int = field(default_factory=lambda: int(_str("SEMANTIC_MAX_MESSAGES", "4")))

    router_cheap_model: str = field(default_factory=lambda: _str("ROUTER_CHEAP_MODEL", "ollama/gemma3:4b"))
    router_strong_model: str = field(default_factory=lambda: _str("ROUTER_STRONG_MODEL", "ollama/gemma3:12b"))
    router_mode: str = field(default_factory=lambda: _str("ROUTER_MODE", "classifier"))
    router_model_path: Path = field(default_factory=lambda: ROOT / "data" / "router_clf.joblib")

    db_path: str = field(default_factory=lambda: _str("DB_PATH", str(ROOT / "tokensaver.db")))
    pricing_path: Path = field(default_factory=lambda: ROOT / "data" / "pricing.json")


AUTO_MODEL = "tokensaver/auto"
