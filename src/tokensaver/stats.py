"""Read-only analytics over the request log, used by /stats and the dashboard."""
from __future__ import annotations

import time

from .db import Database


def totals(db: Database) -> dict:
    r = db.query(
        """SELECT COUNT(*) n, COALESCE(SUM(cost_usd),0) cost, COALESCE(SUM(baseline_cost_usd),0) base,
                  COALESCE(AVG(latency_ms),0) lat,
                  SUM(cache_status='exact_hit') exact, SUM(cache_status='semantic_hit') sem,
                  SUM(cache_status='miss') miss, SUM(cache_status='error') err, SUM(routed) routed,
                  SUM(route_tier='easy') easy, COALESCE(SUM(prompt_tokens+completion_tokens),0) tokens
           FROM requests"""
    )[0]
    n = r["n"] or 0
    ok = n - (r["err"] or 0)
    hits = (r["exact"] or 0) + (r["sem"] or 0)
    saved = r["base"] - r["cost"]
    lat_hit = db.query("SELECT COALESCE(AVG(latency_ms),0) v FROM requests WHERE cache_status IN ('exact_hit','semantic_hit')")[0]["v"]
    lat_miss = db.query("SELECT COALESCE(AVG(latency_ms),0) v FROM requests WHERE cache_status='miss'")[0]["v"]
    return {
        "requests": n,
        "errors": r["err"] or 0,
        "total_cost_usd": round(r["cost"], 8),
        "cost_without_tokensaver_usd": round(r["base"], 8),
        "money_saved_usd": round(saved, 8),
        "percent_saved": round(100 * saved / r["base"], 2) if r["base"] else 0.0,
        "avg_latency_ms": round(r["lat"], 1),
        "avg_latency_hit_ms": round(lat_hit, 1),
        "avg_latency_miss_ms": round(lat_miss, 1),
        "cache_hit_rate": round(100 * hits / ok, 2) if ok else 0.0,
        "exact_hits": r["exact"] or 0,
        "semantic_hits": r["sem"] or 0,
        "misses": r["miss"] or 0,
        "routed": r["routed"] or 0,
        "routed_to_cheap": r["easy"] or 0,
        "tokens": r["tokens"],
    }


def timeseries(db: Database, bucket: str = "hour", since_hours: float = 24 * 7) -> list[dict]:
    size = {"minute": 60, "hour": 3600, "day": 86400}.get(bucket, 3600)
    since = time.time() - since_hours * 3600
    rows = db.query(
        f"""SELECT CAST(ts/{size} AS INTEGER)*{size} t, COUNT(*) requests, SUM(cost_usd) cost,
                   SUM(baseline_cost_usd) baseline, SUM(cache_status IN ('exact_hit','semantic_hit')) hits
            FROM requests WHERE ts >= ? GROUP BY t ORDER BY t""",
        (since,),
    )
    cum_cost = cum_base = 0.0
    out = []
    for r in rows:
        cum_cost += r["cost"] or 0
        cum_base += r["baseline"] or 0
        out.append({"t": r["t"], "requests": r["requests"], "hits": r["hits"] or 0,
                    "cost": round(r["cost"] or 0, 8), "baseline": round(r["baseline"] or 0, 8),
                    "cum_cost": round(cum_cost, 8), "cum_baseline": round(cum_base, 8)})
    return out


def by_model(db: Database) -> list[dict]:
    return db.query(
        """SELECT model_used model, COUNT(*) requests, ROUND(SUM(cost_usd), 8) cost,
                  SUM(cache_status IN ('exact_hit','semantic_hit')) hits, ROUND(AVG(latency_ms),1) avg_latency_ms
           FROM requests WHERE cache_status != 'error' GROUP BY model_used ORDER BY requests DESC"""
    )


def recent(db: Database, limit: int = 50, offset: int = 0) -> dict:
    total = db.query("SELECT COUNT(*) n FROM requests")[0]["n"]
    rows = db.query(
        """SELECT id, ts, model_requested, model_used, prompt_tokens, completion_tokens, cost_usd, baseline_cost_usd,
                  latency_ms, cache_status, routed, route_tier, prompt_preview, status_code
           FROM requests ORDER BY id DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    return {"total": total, "items": rows}
