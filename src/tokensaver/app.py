"""FastAPI app: OpenAI-compatible endpoint + stats API + dashboard."""
from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import stats
from .config import AUTO_MODEL, ROOT, Settings
from .db import Database
from .embeddings import Embedder, MiniLMEmbedder
from .gateway import Gateway
from .pricing import PriceBook
from .router import build_router
from .semantic import SemanticCache

DASHBOARD_DIST = ROOT / "dashboard" / "dist"


def create_app(settings: Settings | None = None, embedder: Embedder | None = None,
               transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    s = settings or Settings()
    emb = embedder if embedder is not None else MiniLMEmbedder()
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(s.db_path)
        client = httpx.AsyncClient(transport=transport) if transport else httpx.AsyncClient()
        semantic = SemanticCache(db, emb, s.semantic_threshold, s.cache_ttl_seconds, s.semantic_max_messages) if s.semantic_enabled else None
        router = build_router(s.router_mode, emb, s.router_model_path)
        state.update(db=db, client=client, router=router, prices=PriceBook(s.pricing_path), semantic=semantic)
        state["gw"] = Gateway(s, db, state["prices"], client, semantic, router)
        yield
        await client.aclose()

    app = FastAPI(title="TokenSaver", version="1.0.0", lifespan=lifespan,
                  description="OpenAI-compatible LLM gateway that cuts AI cost with caching and smart routing.")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-TokenSaver-Cache-Status", "X-TokenSaver-Model", "X-TokenSaver-Route",
                                       "X-TokenSaver-Similarity", "X-TokenSaver-Cost-USD", "X-TokenSaver-Fallback"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "router": type(state["router"]).__name__,
                "semantic_cache": state["semantic"] is not None, "time": time.time()}

    @app.get("/v1/models")
    async def models():
        ids = [AUTO_MODEL, s.router_cheap_model, s.router_strong_model]
        return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "tokensaver"} for i in ids]}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, x_tokensaver_cache: str | None = Header(default=None)):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"error": {"message": "Body must be JSON", "type": "invalid_request_error"}}, 400)
        if not isinstance(body.get("messages"), list) or not body["messages"]:
            return JSONResponse({"error": {"message": "'messages' must be a non-empty list", "type": "invalid_request_error"}}, 400)
        skip = (x_tokensaver_cache or "").lower() == "skip"
        result = await state["gw"].handle(body, skip_cache=skip)
        if body.get("stream") and result.status == 200:
            return StreamingResponse(_as_sse(result.response), media_type="text/event-stream", headers=result.headers)
        return JSONResponse(result.response, result.status, headers=result.headers)

    # ---------------- stats ----------------
    @app.get("/stats")
    async def get_stats():
        return stats.totals(state["db"])

    @app.get("/stats/timeseries")
    async def get_timeseries(bucket: str = Query("hour", pattern="^(minute|hour|day)$"), since_hours: float = 168):
        return stats.timeseries(state["db"], bucket, since_hours)

    @app.get("/stats/models")
    async def get_models():
        return stats.by_model(state["db"])

    @app.get("/requests")
    async def get_requests(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        return stats.recent(state["db"], limit, offset)

    @app.get("/router/explain")
    async def explain(prompt: str):
        d = state["router"].decide(prompt)
        model = s.router_cheap_model if d.tier == "easy" else s.router_strong_model
        return {"tier": d.tier, "score": round(d.score, 3), "method": d.method, "reasons": d.reasons, "model": model}

    @app.get("/config")
    async def config():
        return {"cheap_model": s.router_cheap_model, "strong_model": s.router_strong_model,
                "semantic_threshold": s.semantic_threshold, "cache_ttl_seconds": s.cache_ttl_seconds,
                "cache_max_temperature": s.cache_max_temperature, "router_mode": type(state["router"]).__name__,
                "openrouter_configured": bool(s.openrouter_api_key)}

    @app.get("/benchmark")
    async def benchmark():
        f = ROOT / "benchmark" / "results.json"
        if not f.exists():
            return JSONResponse({"error": "no benchmark yet"}, 404)
        return json.loads(f.read_text(encoding="utf-8"))

    @app.post("/admin/reset")
    async def reset(what: str = Query("all", pattern="^(all|cache|stats)$")):
        if what in ("all", "cache"):
            state["db"].clear_caches()
            if state["semantic"]:
                state["semantic"].clear()
        if what in ("all", "stats"):
            state["db"].clear_requests()
        return {"ok": True, "reset": what}

    # ---------------- dashboard ----------------
    if DASHBOARD_DIST.exists():
        app.mount("/dashboard/assets", StaticFiles(directory=DASHBOARD_DIST / "assets"), name="assets")

        @app.get("/dashboard/{path:path}")
        async def dashboard(path: str = ""):
            f = DASHBOARD_DIST / path
            return FileResponse(f if path and f.is_file() else DASHBOARD_DIST / "index.html")

        @app.get("/")
        async def root():
            return RedirectResponse("/dashboard/")

    return app


def _as_sse(resp: dict):
    """Serve a complete answer as an OpenAI-style stream so `stream=True` clients work too."""
    choice = (resp.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    base = {"id": resp.get("id", "tokensaver"), "object": "chat.completion.chunk",
            "created": resp.get("created", int(time.time())), "model": resp.get("model")}
    chunk = 48
    first = True
    for i in range(0, max(len(content), 1), chunk):
        delta = {"content": content[i:i + chunk]}
        if first:
            delta["role"] = "assistant"
            first = False
        yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]})}\n\n"
    yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': choice.get('finish_reason', 'stop')}], 'usage': resp.get('usage')})}\n\n"
    yield "data: [DONE]\n\n"


app = create_app()
