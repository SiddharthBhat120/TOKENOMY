"""Generate data/router_prompts.csv: ~300 prompts labelled easy (0) / hard (1).

EASY = a small 3B model answers it well: lookups, short translations, greetings,
       simple definitions, formatting, one-line facts, FAQ-style support questions.
HARD = needs a stronger model: multi-step reasoning, code, maths, design, analysis,
       long constrained writing, debugging.
Review the CSV by hand before training; fix any label you disagree with.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

random.seed(7)
OUT = Path(__file__).resolve().parents[1] / "data" / "router_prompts.csv"

EASY_TEMPLATES = [
    "Translate '{w}' to {lang}.", "What is the capital of {country}?", "Define {term} in one sentence.",
    "What does {abbr} stand for?", "Say hello in {lang}.", "Spell '{w}' backwards.", "Is {n} an even number?",
    "Give me a synonym for '{adj}'.", "What is the opposite of '{adj}'?", "Convert {n} km to miles.",
    "What time zone is {country} in?", "Who wrote '{book}'?", "Fix the spelling: '{typo}'.",
    "How do I reset my password?", "What are your support hours?", "Where can I download my invoice?",
    "How do I change my email address?", "Can I cancel my order?", "What payment methods do you accept?",
    "How long does delivery take to {city}?", "Is there a mobile app?", "How do I contact customer care?",
    "Thanks, that's all!", "Good morning!", "What is {a} plus {b}?", "Make this title case: '{phrase}'.",
    "Summarize in one line: '{phrase}'.", "Give me 3 names for a {pet}.", "What colour is a ripe {fruit}?",
    "Is {fruit} a fruit or a vegetable?", "What is the plural of '{w}'?", "Rewrite politely: 'send it now'.",
]
HARD_TEMPLATES = [
    "Design a scalable {system} that handles {n} thousand requests per second and explain the trade-offs.",
    "Write a Python function that {task}, include type hints and unit tests.",
    "Debug this code and explain the root cause:\n```python\ndef avg(xs):\n    return sum(xs) / len(xs) if xs else xs[0]\n```",
    "Prove that the square root of {p} is irrational.", "Analyze the pros and cons of {a1} versus {a2} for a startup.",
    "Explain step by step how {algo} works and give its time complexity.",
    "Compare {a1} and {a2} for building a {system}; recommend one with justification.",
    "Write a 500-word essay on {topic} with at least three cited arguments and a counter-argument.",
    "Optimize this SQL query and explain why it is slow: SELECT * FROM orders o JOIN users u ON o.user_id = u.id WHERE u.city LIKE '%{city}%' ORDER BY o.created_at;",
    "A train leaves at {n}:00 at 80 km/h, another at {m}:30 at 100 km/h on the same track. When does the second catch up? Show your working.",
    "Create a project plan for migrating a monolith to microservices, with risks, milestones and rollback strategy.",
    "Refactor this JavaScript to be testable and explain each change:\nfunction f(a){{let r=[];for(var i=0;i<a.length;i++){{if(a[i]%2==0)r.push(a[i]*2)}}return r}}",
    "Derive the formula for the sum of a geometric series and prove it by induction.",
    "Evaluate the ethical implications of {topic} and propose a policy framework.",
    "Write a regex that validates {thing} and explain every part; list edge cases it must reject.",
    "Given a probability of {pct}% per day, what is the chance of at least one event in a week? Explain.",
    "Implement {algo} in TypeScript without using libraries, and analyze its complexity.",
    "Critique this business model: {biz}. Identify hidden risks and suggest experiments to validate it.",
    "Explain why {phenomenon} happens, at the level of a physics undergraduate, with equations.",
    "Draft a database schema for {system} with tables, keys, indexes and justify normalization choices.",
]
F = dict(
    w=["water", "book", "friend", "school", "computer", "river", "child", "mouse"],
    lang=["Hindi", "Kannada", "French", "Spanish", "German", "Tamil", "Japanese"],
    country=["India", "Japan", "Brazil", "Kenya", "Canada", "Nepal", "Egypt"],
    term=["API", "cloud computing", "photosynthesis", "inflation", "a noun", "RAM", "bandwidth"],
    abbr=["HTTP", "NASA", "UPI", "CPU", "GST", "PDF", "URL"],
    n=[2, 7, 12, 15, 42, 100, 9], m=[3, 4, 5], a=[3, 12, 25, 70], b=[4, 9, 30, 11],
    adj=["happy", "fast", "bright", "ancient", "brave", "quiet"],
    book=["Hamlet", "Wings of Fire", "The Guide", "Malgudi Days", "1984"],
    typo=["recieve the pakage", "definately tommorow", "seperate adress"],
    city=["Mangaluru", "Pune", "Delhi", "Chennai", "Karwar"], phrase=["the quick brown fox jumps", "our sale ends on sunday"],
    pet=["cat", "dog", "parrot"], fruit=["mango", "banana", "tomato", "apple"],
    system=["URL shortener", "chat app", "payments ledger", "ride-hailing backend", "hospital records system", "e-commerce cart"],
    task=["merges overlapping intervals", "finds the longest palindromic substring", "parses a CSV with quoted commas",
          "implements an LRU cache", "validates a Sudoku board"],
    p=[2, 3, 5, 7], a1=["PostgreSQL", "REST", "monolith", "React", "Kafka"], a2=["MongoDB", "GraphQL", "microservices", "Angular", "RabbitMQ"],
    algo=["Dijkstra's algorithm", "quicksort", "a B-tree insert", "the Raft consensus protocol", "backpropagation"],
    topic=["AI in hiring", "facial recognition in public spaces", "remote work", "social media for teenagers"],
    thing=["an Indian PAN number", "an IPv6 address", "an email address", "a strong password"],
    pct=[2, 5, 10], biz=["a subscription for home-cooked tiffins", "a marketplace for used textbooks", "drone delivery of medicines"],
    phenomenon=["the sky appears blue", "ice floats on water", "planes generate lift"],
)


def fill(t: str) -> str:
    return t.format(**{k: random.choice(v) for k, v in F.items()})


def build(n_each: int = 150) -> list[tuple[str, int]]:
    rows: set[tuple[str, int]] = set()
    while len([r for r in rows if r[1] == 0]) < n_each:
        rows.add((fill(random.choice(EASY_TEMPLATES)), 0))
    while len([r for r in rows if r[1] == 1]) < n_each:
        rows.add((fill(random.choice(HARD_TEMPLATES)), 1))
    out = list(rows)
    random.shuffle(out)
    return out


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    rows = build()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["prompt", "label"])
        w.writerows(rows)
    print(f"wrote {len(rows)} prompts -> {OUT}")
