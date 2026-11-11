"""Text embeddings for the semantic cache and the router classifier.

Uses sentence-transformers all-MiniLM-L6-v2 (384-dim, runs on CPU, free).
The model is loaded lazily once. Tests use HashEmbedder so they stay fast and offline.
"""
from __future__ import annotations

import hashlib
import threading
from typing import Protocol

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class MiniLMEmbedder:
    dim = 384

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(MODEL_NAME, device="cpu")
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._load().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vecs.astype(np.float32)


class HashEmbedder:
    """Deterministic bag-of-words embedder for tests (no model download)."""

    dim = 256

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for word in t.lower().replace("?", " ").replace(",", " ").split():
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out
