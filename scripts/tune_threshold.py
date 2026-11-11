"""Try semantic-cache thresholds on prompt pairs and print how each behaves.

    python scripts/tune_threshold.py
'same' pairs SHOULD hit the cache; 'different' pairs must NOT (a wrong hit = a wrong answer).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tokenomy.embeddings import MiniLMEmbedder  # noqa: E402
from tokenomy.semantic import same_key_facts  # noqa: E402

PAIRS = [
    ("What's the capital of India?", "India's capital city?", "same"),
    ("How do I reset my password?", "I forgot my password, how can I reset it?", "same"),
    ("What are your support hours?", "When is customer support available?", "same"),
    ("How long does delivery take?", "How many days for shipping?", "same"),
    ("Can I cancel my order?", "Is it possible to cancel an order I placed?", "same"),
    ("What payment methods do you accept?", "Which ways can I pay?", "same"),
    ("Translate hello to Hindi", "How do you say hello in Hindi?", "same"),
    ("Do you ship internationally?", "Can you deliver outside India?", "same"),
    ("Flights to Delhi from Mumbai", "Flights from Delhi to Mumbai", "different"),
    ("How do I cancel my order?", "How do I place an order?", "different"),
    ("Translate hello to Hindi", "Translate hello to Tamil", "different"),
    ("Is the store open on Sunday?", "Is the store open on Monday?", "different"),
    ("What is 15% of 200?", "What is 20% of 150?", "different"),
    ("Refund to my credit card", "Refund to my UPI account", "different"),
    ("Best laptop under 50000 rupees", "Best laptop under 80000 rupees", "different"),
    ("How do I delete my account?", "How do I create an account?", "different"),
]


def main() -> None:
    emb = MiniLMEmbedder()
    a = emb.embed([p[0] for p in PAIRS])
    b = emb.embed([p[1] for p in PAIRS])
    sims = (a * b).sum(axis=1)
    print(f"{'similarity':>10}  {'type':9}  pair")
    for (x, y, kind), s in sorted(zip(PAIRS, sims), key=lambda z: -z[1]):
        print(f"{s:10.3f}  {kind:9}  {x!r} ~ {y!r}")
    guard = [same_key_facts(x, y) for x, y, _ in PAIRS]
    print("\n           similarity only          similarity + key-facts guard")
    print("threshold  same-hit   WRONG-hit     same-hit   WRONG-hit")
    for t in (0.80, 0.82, 0.85, 0.88, 0.90, 0.92, 0.94):
        def rate(kind: str, use_guard: bool) -> str:
            hits = [s >= t and (g or not use_guard) for (_, _, k), s, g in zip(PAIRS, sims, guard) if k == kind]
            return f"{sum(hits)}/{len(hits)}"
        print(f"   {t:.2f}     {rate('same', False):>5}      {rate('different', False):>5}        "
              f"{rate('same', True):>5}      {rate('different', True):>5}")


if __name__ == "__main__":
    main()
