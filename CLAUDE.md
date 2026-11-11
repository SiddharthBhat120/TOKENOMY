# TokenSaver

OpenAI-compatible LLM gateway (Python/FastAPI) that sits between apps and LLM providers
(Ollama locally, OpenRouter in the cloud) and cuts cost with exact caching, semantic caching
and complexity-based model routing. A React dashboard shows the savings.

## Stack
- FastAPI + httpx (async) — `src/tokensaver/`
- SQLite (request log, exact cache, semantic cache) — `db.py`
- sentence-transformers `all-MiniLM-L6-v2` embeddings, NumPy cosine search — `embeddings.py`, `semantic.py`
- scikit-learn logistic-regression router on embeddings — `router.py`, `scripts/train_router.py`
- React + Vite + Recharts dashboard — `dashboard/`, served by FastAPI at `/dashboard/`
- Docker + docker-compose, GitHub Actions CI

## Layout
```
src/tokensaver/
  app.py        FastAPI routes: /v1/chat/completions, /stats*, /requests, /router/explain, /benchmark, /dashboard
  gateway.py    pipeline: exact cache -> semantic cache -> router -> provider -> log
  cache.py      exact-cache key + "is this request cacheable?" (temperature rule)
  semantic.py   embedding search + key-facts guard (numbers, days, names, to/from, opposites)
  router.py     RuleScorer (v1) and ClassifierRouter (v2)
  providers.py  "ollama/<model>" -> local Ollama, anything else -> OpenRouter
  pricing.py    USD per 1M tokens from data/pricing.json (OpenRouter public prices)
  stats.py      analytics queries for the dashboard
  config.py     settings from .env
scripts/        update_pricing, make_router_dataset, train_router, tune_threshold
benchmark/      generate_prompts.py, run.py -> results.json / results.md / *.png
tests/          pytest, fully offline (fake upstream + hash embedder)
```

## Rules
- Type hints, small functions, docstrings that say *why*.
- Every feature has a pytest test; tests never call a real model or download anything.
- All config through `.env` (see `.env.example`); never commit `.env`.
- Zero cost: only free tools/models (Ollama local, OpenRouter free tier).

## Commands
```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m uvicorn tokensaver.app:app --app-dir src --port 8000
cd dashboard && npm install && npm run build      # or npm run dev (port 5173)
python benchmark/run.py --limit 40                # quick benchmark
```
