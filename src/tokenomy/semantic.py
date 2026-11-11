"""Semantic cache: reuse an answer when a *similar* prompt was already answered.

Scope = (model, system prompt). Two prompts only match inside the same scope, so a
cached answer is never served under a different model or a different persona.

Risk: prompts can look alike but mean different things ("flights to Delhi" vs
"flights from Delhi"). The cosine-similarity threshold (default 0.92) is the guard;
`scripts/tune_threshold.py` shows how each threshold behaves on tricky pairs.
"""
from __future__ import annotations

import hashlib
import re
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from .db import Database
from .embeddings import Embedder


_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today", "tomorrow", "yesterday",
         "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"}
_NEGATIONS = {"not", "no", "never", "don't", "doesn't", "isn't", "can't", "cannot", "won't", "without"}
_DIRECTIONAL = {"to", "from", "into", "before", "after", "above", "below", "under", "over"}
_OPPOSITES = [{"cancel", "place"}, {"delete", "create"}, {"add", "remove"}, {"buy", "sell"}, {"increase", "decrease"},
              {"enable", "disable"}, {"open", "close"}, {"start", "stop"}, {"credit", "debit"}, {"login", "logout"}]
_STOP_CAPS = {"I", "What", "How", "Is", "Can", "Do", "Does", "Where", "When", "Why", "Who", "Which", "Please", "The", "A", "An",
              "Translate", "Tell", "Give", "Show", "Best", "Refund", "Flights", "Cheap"}


def _key_facts(text: str) -> dict:
    words = [w[:-2] if w.lower().endswith("'s") else w for w in _WORD.findall(text)]
    lower = [w.lower() for w in words]
    proper = {w.lower() for i, w in enumerate(words) if w[0].isupper() and w not in _STOP_CAPS}
    # any word after "to/in" etc. that names a language/place is usually capitalised; also keep lower-case place names
    direction = {(p, lower[i + 1]) for i, p in enumerate(lower[:-1]) if p in _DIRECTIONAL}
    return {
        "numbers": set(_NUM.findall(text)),
        "days": {w for w in lower if w in _DAYS},
        "negated": bool(_NEGATIONS & set(lower)),
        "proper": proper,
        "direction": direction,
        "lower": set(lower),
    }


def same_key_facts(a: str, b: str) -> bool:
    """Guard against 'looks similar, means something else'. True = safe to reuse the answer."""
    fa, fb = _key_facts(a), _key_facts(b)
    if fa["numbers"] != fb["numbers"] or fa["days"] != fb["days"] or fa["negated"] != fb["negated"]:
        return False
    if fa["proper"] and fb["proper"] and fa["proper"] != fb["proper"]:
        return False
    # same directional word followed by a different word -> different meaning ("to Delhi" vs "to Mumbai")
    da, db = dict(), dict()
    for p, w in fa["direction"]:
        da.setdefault(p, set()).add(w)
    for p, w in fb["direction"]:
        db.setdefault(p, set()).add(w)
    for p in set(da) & set(db):
        if da[p] != db[p]:
            return False
    for pair in _OPPOSITES:
        if (pair & fa["lower"]) and (pair & fb["lower"]) and (pair & fa["lower"]) != (pair & fb["lower"]):
            return False
    return True


@dataclass
class SemanticHit:
    response: dict
    similarity: float
    matched_prompt: str


def _system_prompt(messages: list[dict[str, Any]]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")


def last_user_message(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"].strip()
    return ""


def scope_for(model: str, messages: list[dict[str, Any]]) -> str:
    sys_hash = hashlib.sha1(_system_prompt(messages).encode()).hexdigest()[:12]
    return f"{model}|{sys_hash}"


class SemanticCache:
    def __init__(self, db: Database, embedder: Embedder, threshold: float, ttl: int, max_messages: int) -> None:
        self.db = db
        self.embedder = embedder
        self.threshold = threshold
        self.ttl = ttl
        self.max_messages = max_messages
        self._lock = threading.Lock()
        # scope -> (ids, matrix [n, dim], prompts, created_at)
        self._index: dict[str, tuple[list[int], np.ndarray, list[str], list[float]]] = {}
        self._load()

    def _load(self) -> None:
        rows = self.db.query("SELECT id, scope, prompt, embedding, created_at FROM semantic_cache ORDER BY id")
        for r in rows:
            vec = np.frombuffer(r["embedding"], dtype=np.float32)
            if vec.shape[0] != self.embedder.dim:
                continue  # embedded with another model; ignore
            self._append(r["scope"], r["id"], vec, r["prompt"], r["created_at"])

    def _append(self, scope: str, row_id: int, vec: np.ndarray, prompt: str, created: float) -> None:
        ids, mat, prompts, times = self._index.get(scope, ([], np.zeros((0, self.embedder.dim), np.float32), [], []))
        self._index[scope] = (ids + [row_id], np.vstack([mat, vec[None, :]]), prompts + [prompt], times + [created])

    def applicable(self, messages: list[dict[str, Any]]) -> bool:
        """Only short conversations: in long chats, the meaning depends on earlier turns."""
        non_system = [m for m in messages if m.get("role") != "system"]
        return 0 < len(non_system) <= self.max_messages and bool(last_user_message(messages)) and len(non_system) == 1

    def lookup(self, model: str, messages: list[dict[str, Any]]) -> SemanticHit | None:
        prompt = last_user_message(messages)
        scope = scope_for(model, messages)
        with self._lock:
            entry = self._index.get(scope)
            if not entry or not len(entry[0]):
                return None
            ids, mat, prompts, times = entry
            q = self.embedder.embed([prompt])[0]
            sims = mat @ q
            now = time.time()
            sims = np.where(np.array(times) >= now - self.ttl, sims, -1.0)
            order = np.argsort(-sims)[:5]
            candidates = [(int(i), float(sims[i]), prompts[int(i)], ids[int(i)]) for i in order if sims[i] >= self.threshold]
        for _, sim, matched, row_id in candidates:
            if not same_key_facts(prompt, matched):
                continue  # similar wording, different facts -> not safe
            row = self.db.query("SELECT response FROM semantic_cache WHERE id=?", (row_id,))
            if row:
                return SemanticHit(json.loads(row[0]["response"]), sim, matched)
        return None

    def store(self, model: str, messages: list[dict[str, Any]], response: dict) -> None:
        prompt = last_user_message(messages)
        scope = scope_for(model, messages)
        vec = self.embedder.embed([prompt])[0].astype(np.float32)
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO semantic_cache (scope, prompt, embedding, response, created_at) VALUES (?,?,?,?,?)",
            (scope, prompt, vec.tobytes(), json.dumps(response), now),
        )
        with self._lock:
            self._append(scope, int(cur.lastrowid), vec, prompt, now)

    def clear(self) -> None:
        with self._lock:
            self._index.clear()
