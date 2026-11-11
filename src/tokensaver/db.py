"""SQLite storage: request log, exact cache, semantic cache."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model_requested TEXT NOT NULL,
    model_used TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    baseline_cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0,
    cache_status TEXT NOT NULL,
    routed INTEGER NOT NULL DEFAULT 0,
    route_tier TEXT,
    prompt_preview TEXT,
    status_code INTEGER NOT NULL DEFAULT 200
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);

CREATE TABLE IF NOT EXISTS exact_cache (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    prompt TEXT NOT NULL,
    embedding BLOB NOT NULL,
    response TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_scope ON semantic_cache(scope);
"""


@dataclass
class RequestLog:
    model_requested: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    baseline_cost_usd: float
    latency_ms: float
    cache_status: str  # miss | exact_hit | semantic_hit | bypass | error
    routed: bool = False
    route_tier: str | None = None
    prompt_preview: str = ""
    status_code: int = 200


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---------- generic ----------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # ---------- request log ----------
    def log_request(self, r: RequestLog) -> None:
        self.execute(
            """INSERT INTO requests (ts, model_requested, model_used, prompt_tokens, completion_tokens,
               cost_usd, baseline_cost_usd, latency_ms, cache_status, routed, route_tier, prompt_preview, status_code)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), r.model_requested, r.model_used, r.prompt_tokens, r.completion_tokens, r.cost_usd,
             r.baseline_cost_usd, r.latency_ms, r.cache_status, int(r.routed), r.route_tier,
             r.prompt_preview[:200], r.status_code),
        )

    # ---------- exact cache ----------
    def exact_get(self, key: str, ttl: int) -> dict | None:
        rows = self.query("SELECT response, created_at FROM exact_cache WHERE key=?", (key,))
        if not rows:
            return None
        if time.time() - rows[0]["created_at"] > ttl:
            self.execute("DELETE FROM exact_cache WHERE key=?", (key,))
            return None
        return json.loads(rows[0]["response"])

    def exact_put(self, key: str, model: str, response: dict) -> None:
        self.execute(
            "INSERT OR REPLACE INTO exact_cache (key, model, response, created_at) VALUES (?,?,?,?)",
            (key, model, json.dumps(response), time.time()),
        )

    def clear_caches(self) -> None:
        self.execute("DELETE FROM exact_cache")
        self.execute("DELETE FROM semantic_cache")

    def clear_requests(self) -> None:
        self.execute("DELETE FROM requests")
