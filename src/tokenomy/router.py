"""Complexity-based routing: EASY prompts -> cheap model, HARD prompts -> strong model.

v1 `RuleScorer`: transparent heuristics (length, code, maths, reasoning words, constraints).
v2 `ClassifierRouter`: logistic regression on MiniLM embeddings, trained by
   scripts/train_router.py on data/router_prompts.csv. Falls back to rules if the
   model file is missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .embeddings import Embedder

HARD_WORDS = {
    "analyze", "analyse", "prove", "design", "architect", "step by step", "derive", "compare", "evaluate",
    "optimize", "optimise", "debug", "refactor", "explain why", "trade-off", "tradeoff", "strategy",
    "implement", "algorithm", "complexity", "critique", "justify", "plan", "essay", "proof",
}
CODE_RE = re.compile(r"```|\bdef |\bclass |\bfunction\b|=>|;\s*$|\bSELECT\b|\bimport |#include|\{\s*$", re.M)
MATH_RE = re.compile(r"\d+\s*[\^*/]\s*\d+|\bintegral\b|\bderivative\b|\bmatrix\b|\bprobability\b|∑|√|\bequation\b", re.I)
CONSTRAINT_RE = re.compile(r"\b(must|should|at least|at most|exactly|without|only|ensure|no more than)\b", re.I)


@dataclass
class RouteDecision:
    tier: str  # "easy" | "hard"
    score: float  # 0..1, higher = harder
    method: str  # "rules" | "classifier"
    reasons: list[str] = field(default_factory=list)


class RuleScorer:
    threshold = 0.5

    def decide(self, prompt: str) -> RouteDecision:
        p = prompt.lower()
        score, reasons = 0.0, []
        words = len(prompt.split())
        if words > 120:
            score += 0.4; reasons.append(f"long prompt ({words} words)")
        elif words > 50:
            score += 0.2; reasons.append(f"medium prompt ({words} words)")
        if CODE_RE.search(prompt):
            score += 0.4; reasons.append("contains code")
        if MATH_RE.search(prompt):
            score += 0.3; reasons.append("maths")
        hits = [w for w in HARD_WORDS if w in p]
        if hits:
            score += min(0.5, 0.25 * len(hits)); reasons.append("reasoning words: " + ", ".join(sorted(hits)[:3]))
        constraints = len(CONSTRAINT_RE.findall(prompt))
        if constraints >= 2:
            score += 0.2; reasons.append(f"{constraints} constraints")
        score = min(1.0, score)
        return RouteDecision("hard" if score >= self.threshold else "easy", score, "rules", reasons or ["short, simple request"])


class ClassifierRouter:
    def __init__(self, embedder: Embedder, model_path: Path) -> None:
        import joblib

        self.embedder = embedder
        bundle = joblib.load(model_path)
        self.clf = bundle["clf"]
        self.threshold = float(bundle.get("threshold", 0.5))
        self.rules = RuleScorer()

    def decide(self, prompt: str) -> RouteDecision:
        vec = self.embedder.embed([prompt])
        p_hard = float(self.clf.predict_proba(vec)[0][1])
        rules = self.rules.decide(prompt)
        # blend: the classifier understands meaning, rules catch obvious code/maths/length
        score = 0.75 * p_hard + 0.25 * rules.score
        tier = "hard" if score >= self.threshold else "easy"
        return RouteDecision(tier, score, "classifier", [f"classifier p(hard)={p_hard:.2f}"] + rules.reasons)


def build_router(mode: str, embedder: Embedder | None, model_path: Path):
    if mode == "classifier" and embedder is not None and model_path.exists():
        try:
            return ClassifierRouter(embedder, model_path)
        except Exception:  # corrupt / incompatible model file
            pass
    return RuleScorer()
