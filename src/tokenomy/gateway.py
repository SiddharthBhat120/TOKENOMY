"""The request pipeline: exact cache -> semantic cache -> router -> provider -> log."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import providers
from .cache import cache_key, is_cacheable
from .config import AUTO_MODEL, Settings
from .db import Database, RequestLog
from .pricing import PriceBook
from .semantic import SemanticCache, last_user_message


@dataclass
class GatewayResult:
    response: dict
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)


def _usage(resp: dict) -> tuple[int, int]:
    u = resp.get("usage") or {}
    return int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


class Gateway:
    def __init__(self, s: Settings, db: Database, prices: PriceBook, client: httpx.AsyncClient,
                 semantic: SemanticCache | None, router) -> None:
        self.s, self.db, self.prices, self.client = s, db, prices, client
        self.semantic, self.router = semantic, router

    async def handle(self, body: dict[str, Any], skip_cache: bool = False) -> GatewayResult:
        t0 = time.perf_counter()
        requested = str(body.get("model") or AUTO_MODEL)
        messages = body.get("messages") or []
        prompt = last_user_message(messages)
        routed = requested == AUTO_MODEL
        route_tier, route_reason = None, ""
        if routed:
            decision = self.router.decide(prompt)
            route_tier = decision.tier
            route_reason = "; ".join(decision.reasons)[:180]
            model_used = self.s.router_cheap_model if decision.tier == "easy" else self.s.router_strong_model
            baseline_model = self.s.router_strong_model  # without Tokenomy everything goes to the strong model
        else:
            model_used = baseline_model = requested

        cacheable = not skip_cache and is_cacheable(body, self.s.cache_max_temperature)
        key = cache_key(requested, body) if cacheable else None
        base_headers = {"X-Tokenomy-Model": model_used}
        if route_tier:
            base_headers["X-Tokenomy-Route"] = route_tier

        # 1) exact cache
        if key:
            hit = self.db.exact_get(key, self.s.cache_ttl_seconds)
            if hit is not None:
                return self._finish(hit, requested, hit.get("_ts_model", model_used), baseline_model, "exact_hit",
                                    t0, routed, route_tier, prompt, base_headers, cost_zero=True)

        # 2) semantic cache
        use_semantic = bool(cacheable and self.semantic and self.s.semantic_enabled and self.semantic.applicable(messages))
        if use_semantic:
            sem = self.semantic.lookup(requested, messages)
            if sem is not None:
                headers = {**base_headers, "X-Tokenomy-Similarity": f"{sem.similarity:.3f}"}
                return self._finish(sem.response, requested, sem.response.get("_ts_model", model_used), baseline_model,
                                    "semantic_hit", t0, routed, route_tier, prompt, headers, cost_zero=True,
                                    extra={"similarity": round(sem.similarity, 4), "matched_prompt": sem.matched_prompt})

        # 3) provider (with fallback from cheap -> strong)
        fallback = False
        try:
            resp = await providers.chat(self.client, model_used, body, self.s)
        except providers.UpstreamError as e:
            if routed and model_used != self.s.router_strong_model:
                fallback = True
                model_used = self.s.router_strong_model
                base_headers["X-Tokenomy-Model"] = model_used
                try:
                    resp = await providers.chat(self.client, model_used, body, self.s)
                except providers.UpstreamError as e2:
                    return self._error(e2, requested, model_used, t0, routed, route_tier, prompt)
            else:
                return self._error(e, requested, model_used, t0, routed, route_tier, prompt)

        resp["_ts_model"] = model_used
        if key:
            self.db.exact_put(key, requested, resp)
            if use_semantic:
                self.semantic.store(requested, messages, resp)
        if fallback:
            base_headers["X-Tokenomy-Fallback"] = "true"
        return self._finish(resp, requested, model_used, baseline_model, "miss", t0, routed, route_tier, prompt,
                            base_headers, extra={"route_reason": route_reason} if route_reason else None)

    # ------------------------------------------------------------------
    def _finish(self, resp: dict, requested: str, model_used: str, baseline_model: str, status: str, t0: float,
                routed: bool, tier: str | None, prompt: str, headers: dict[str, str], cost_zero: bool = False,
                extra: dict | None = None) -> GatewayResult:
        pt, ct = _usage(resp)
        cost = 0.0 if cost_zero else self.prices.cost(model_used, pt, ct)
        baseline = self.prices.cost(baseline_model, pt, ct)
        latency = (time.perf_counter() - t0) * 1000
        self.db.log_request(RequestLog(requested, model_used, pt, ct, cost, baseline, latency, status, routed, tier, prompt))
        out = {k: v for k, v in resp.items() if not k.startswith("_ts")}
        out["model"] = requested
        out["x_tokenomy"] = {
            "cache_status": status, "model_used": model_used, "route": tier, "cost_usd": round(cost, 8),
            "cost_without_tokenomy_usd": round(baseline, 8), "latency_ms": round(latency, 1), **(extra or {}),
        }
        h = {**headers, "X-Tokenomy-Cache-Status": status, "X-Tokenomy-Cost-USD": f"{cost:.8f}"}
        return GatewayResult(out, 200, h)

    def _error(self, e: providers.UpstreamError, requested: str, model_used: str, t0: float, routed: bool,
               tier: str | None, prompt: str) -> GatewayResult:
        latency = (time.perf_counter() - t0) * 1000
        self.db.log_request(RequestLog(requested, model_used, 0, 0, 0.0, 0.0, latency, "error", routed, tier, prompt, e.status))
        body = {"error": {"message": e.message, "type": "upstream_error", "provider": e.provider, "code": e.status}}
        return GatewayResult(body, e.status, {"X-Tokenomy-Cache-Status": "error"})
