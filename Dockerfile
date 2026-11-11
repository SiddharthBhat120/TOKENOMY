# ---- 1) build the React dashboard ----
FROM node:22-alpine AS dashboard
WORKDIR /dash
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install
COPY dashboard/ ./
RUN npm run build

# ---- 2) Python gateway ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf DB_PATH=/app/state/tokenomy.db
WORKDIR /app
COPY requirements.txt .
# CPU-only torch keeps the image ~1 GB instead of ~5 GB (embeddings are tiny)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt
COPY src/ src/
COPY data/ data/
COPY scripts/ scripts/
COPY --from=dashboard /dash/dist dashboard/dist
# bake the embedding model into the image so the first request is fast
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')"
RUN mkdir -p /app/state
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "tokenomy.app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
