"""Train the v2 router: logistic regression on MiniLM embeddings.

    python scripts/train_router.py
Prints accuracy on a held-out 25% split and saves data/router_clf.joblib.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tokenomy.embeddings import MiniLMEmbedder  # noqa: E402
from tokenomy.router import RuleScorer  # noqa: E402


def main() -> None:
    rows = list(csv.DictReader((ROOT / "data" / "router_prompts.csv").open(encoding="utf-8")))
    texts = [r["prompt"] for r in rows]
    y = np.array([int(r["label"]) for r in rows])
    X = MiniLMEmbedder().embed(texts)
    Xtr, Xte, ytr, yte, ttr, tte = train_test_split(X, y, texts, test_size=0.25, random_state=42, stratify=y)

    clf = LogisticRegression(max_iter=2000, C=2.0).fit(Xtr, ytr)
    pred = clf.predict(Xte)
    acc = (pred == yte).mean()
    rules = RuleScorer()
    rule_acc = np.mean([(rules.decide(t).tier == "hard") == bool(l) for t, l in zip(tte, yte)])

    print(f"train={len(ytr)} test={len(yte)}")
    print(f"classifier accuracy: {acc:.1%}   (rule-based v1 on same split: {rule_acc:.1%})")
    print(confusion_matrix(yte, pred))
    print(classification_report(yte, pred, target_names=["easy", "hard"]))

    clf_full = LogisticRegression(max_iter=2000, C=2.0).fit(X, y)
    out = ROOT / "data" / "router_clf.joblib"
    joblib.dump({"clf": clf_full, "threshold": 0.5, "test_accuracy": float(acc), "rule_accuracy": float(rule_acc)}, out)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
