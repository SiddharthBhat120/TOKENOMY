"""Benchmark: does TokenSaver cut cost without hurting answers?

    python benchmark/run.py            # full 1,000 prompts (needs Ollama + gemma3:4b + gemma3:12b)
    python benchmark/run.py --limit 40 # quick smoke test

A) Baseline  = every prompt sent straight to the STRONG model (what a company does today).
B) TokenSaver = every prompt sent to `tokensaver/auto` (exact cache + smart cache + router).
Quality = the strong model judges B's answer against A's on a random sample (blind, order shuffled).

Note on A: at temperature 0 the same prompt gives the same answer and token count, so A is
measured once per unique prompt and that measured cost/latency is counted for every repeat.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from tokensaver.app import create_app  # noqa: E402
from tokensaver.config import Settings  # noqa: E402
from tokensaver.pricing import PriceBook  # noqa: E402

RAW = HERE / "raw"
MAX_TOKENS = 256
PROJ_STRONG, PROJ_CHEAP = "openai/gpt-4o", "openai/gpt-4o-mini"


def load_prompts(limit: int | None) -> list[dict]:
    rows = [json.loads(l) for l in (HERE / "prompts.jsonl").open(encoding="utf-8")]
    return rows[:limit] if limit else rows


def messages(p: dict) -> list[dict]:
    return [{"role": "system", "content": p["system"]}, {"role": "user", "content": p["text"]}]


def ollama_chat(s: Settings, model: str, msgs: list[dict], **extra) -> tuple[dict, float]:
    t0 = time.perf_counter()
    r = httpx.post(f"{s.ollama_base_url}/chat/completions", timeout=900,
                   json={"model": model.split("/", 1)[1], "messages": msgs, "temperature": 0, "max_tokens": MAX_TOKENS, **extra})
    r.raise_for_status()
    return r.json(), (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------- A: baseline
def run_baseline(s: Settings, prompts: list[dict]) -> dict[str, dict]:
    RAW.mkdir(exist_ok=True)
    f = RAW / "baseline.json"
    done: dict[str, dict] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    todo = [p for p in {p["text"]: p for p in prompts}.values() if p["text"] not in done]
    print(f"[A] baseline: {len(done)} cached, {len(todo)} unique prompts to run on {s.router_strong_model}")
    for i, p in enumerate(todo, 1):
        resp, lat = ollama_chat(s, s.router_strong_model, messages(p))
        u = resp.get("usage", {})
        done[p["text"]] = {"answer": resp["choices"][0]["message"]["content"], "prompt_tokens": u.get("prompt_tokens", 0),
                           "completion_tokens": u.get("completion_tokens", 0), "latency_ms": lat}
        if i % 5 == 0 or i == len(todo):
            f.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
            print(f"    {i}/{len(todo)}  last {lat / 1000:.1f}s")
    return done


# ---------------------------------------------------------------- B: TokenSaver
def run_tokensaver(s: Settings, prompts: list[dict]) -> list[dict]:
    db = RAW / "bench.db"
    for ext in ("", "-wal", "-shm"):
        Path(str(db) + ext).unlink(missing_ok=True)
    s.db_path = str(db)
    s.upstream_timeout = 900
    out = []
    with TestClient(create_app(s)) as c:
        print(f"[B] TokenSaver: router={c.get('/health').json()['router']}, {len(prompts)} prompts")
        t_start = time.time()
        for i, p in enumerate(prompts, 1):
            r = c.post("/v1/chat/completions", json={"model": "tokensaver/auto", "messages": messages(p),
                                                       "temperature": 0, "max_tokens": MAX_TOKENS})
            data = r.json()
            x = data.get("x_tokensaver", {})
            usage = data.get("usage") or {}
            out.append({"id": p["id"], "text": p["text"], "kind": p["kind"], "status": x.get("cache_status", "error"),
                        "model_used": x.get("model_used"), "route": x.get("route"), "cost": x.get("cost_usd", 0.0),
                        "latency_ms": x.get("latency_ms", 0.0), "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "answer": (data.get("choices") or [{}])[0].get("message", {}).get("content", ""),
                        "similarity": x.get("similarity")})
            if i % 50 == 0 or i == len(prompts):
                hits = sum(o["status"] in ("exact_hit", "semantic_hit") for o in out)
                print(f"    {i}/{len(prompts)}  hits {hits}  elapsed {time.time() - t_start:.0f}s")
        stats = c.get("/stats").json()
    (RAW / "tokensaver.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"    gateway stats: {stats['percent_saved']}% saved, hit rate {stats['cache_hit_rate']}%")
    return out


# ---------------------------------------------------------------- quality
JUDGE = """You are grading two answers from a customer-support chatbot for an online store.
Question: {q}

Answer 1:
{a1}

Answer 2:
{a2}

Judge which answer is more helpful and correct for the customer. Minor wording differences do not matter;
treat answers of similar usefulness as a tie. Reply with JSON only: {{"winner": "1" | "2" | "tie", "reason": "<short>"}}"""


def judge(s: Settings, prompts: list[dict], base: dict[str, dict], ts: list[dict], n: int) -> dict:
    rng = random.Random(42)
    sample = rng.sample(ts, min(n, len(ts)))
    dist = {"better": 0, "same": 0, "worse": 0}
    details = []
    print(f"[Q] judging {len(sample)} random TokenSaver answers with {s.router_strong_model}")
    for i, row in enumerate(sample, 1):
        a = base[row["text"]]["answer"].strip()
        b = (row["answer"] or "").strip()
        if not b:
            verdict = "worse"
        elif a == b:
            verdict = "same"  # identical text (e.g. routed to the strong model or exact hit)
        else:
            b_first = rng.random() < 0.5
            a1, a2 = (b, a) if b_first else (a, b)
            resp, _ = ollama_chat(s, s.router_strong_model, [{"role": "user", "content": JUDGE.format(q=row["text"], a1=a1, a2=a2)}],
                                  response_format={"type": "json_object"})
            raw = resp["choices"][0]["message"]["content"]
            m = re.search(r'"winner"\s*:\s*"?(1|2|tie)', raw, re.I)
            w = (m.group(1).lower() if m else "tie")
            if w == "tie":
                verdict = "same"
            else:
                b_won = (w == "1") == b_first
                verdict = "better" if b_won else "worse"
        dist[verdict] += 1
        details.append({"text": row["text"], "status": row["status"], "model_used": row["model_used"], "verdict": verdict})
        if i % 20 == 0:
            print(f"    {i}/{len(sample)}  {dist}")
    (RAW / "judgements.json").write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    eq = dist["better"] + dist["same"]
    return {"sample": len(sample), "judge": s.router_strong_model, "distribution": dist,
            "equal_or_better_pct": round(100 * eq / len(sample), 1) if sample else 0.0}


# ---------------------------------------------------------------- report
def summarize(s: Settings, prompts: list[dict], base: dict[str, dict], ts: list[dict], quality: dict) -> dict:
    prices = PriceBook(s.pricing_path)
    a_cost = sum(prices.cost(s.router_strong_model, base[p["text"]]["prompt_tokens"], base[p["text"]]["completion_tokens"]) for p in prompts)
    a_lat = sum(base[p["text"]]["latency_ms"] for p in prompts) / len(prompts)
    calls = [t for t in ts if t["status"] == "miss"]
    b_cost = sum(t["cost"] for t in ts)
    routed_cheap = sum(t["route"] == "easy" for t in ts)
    hits_exact = sum(t["status"] == "exact_hit" for t in ts)
    hits_sem = sum(t["status"] == "semantic_hit" for t in ts)

    # projection: identical token counts priced as a company using GPT-4o / GPT-4o-mini
    pa = sum(prices.cost(PROJ_STRONG, base[p["text"]]["prompt_tokens"], base[p["text"]]["completion_tokens"]) for p in prompts)
    pb = sum(prices.cost(PROJ_CHEAP if t["model_used"] == s.router_cheap_model else PROJ_STRONG, t["prompt_tokens"], t["completion_tokens"])
             for t in calls)
    return {
        "date": time.strftime("%Y-%m-%d"), "prompts": len(prompts), "unique_prompts": len({p["text"] for p in prompts}),
        "cheap_model": s.router_cheap_model, "strong_model": s.router_strong_model,
        "pricing_note": "OpenRouter list prices of the same open models",
        "baseline": {"calls": len(prompts), "cost_usd": round(a_cost, 6), "avg_latency_ms": round(a_lat, 1)},
        "tokensaver": {"calls": len(calls), "cost_usd": round(b_cost, 6), "avg_latency_ms": round(sum(t["latency_ms"] for t in ts) / len(ts), 1),
                       "exact_hits": hits_exact, "semantic_hits": hits_sem,
                       "cache_hit_rate": round(100 * (hits_exact + hits_sem) / len(ts), 1),
                       "routed_cheap_pct": round(100 * routed_cheap / len(ts), 1),
                       "errors": sum(t["status"] == "error" for t in ts)},
        "percent_saved": round(100 * (a_cost - b_cost) / a_cost, 1) if a_cost else 0.0,
        "quality": quality,
        "projection": {"strong": PROJ_STRONG, "cheap": PROJ_CHEAP, "baseline_usd": round(pa, 4), "tokensaver_usd": round(pb, 4),
                       "percent_saved": round(100 * (pa - pb) / pa, 1) if pa else 0.0},
    }


def write_report(r: dict) -> None:
    (HERE / "results.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    b, t, q, pj = r["baseline"], r["tokensaver"], r["quality"], r["projection"]
    md = f"""# TokenSaver benchmark ({r['date']})

**{r['prompts']:,} customer-support prompts** ({r['unique_prompts']} unique), cheap model `{r['cheap_model']}`, strong model `{r['strong_model']}`.
Costs use {r['pricing_note']} (`data/pricing.json`).

| Metric | Strong model only | TokenSaver |
|---|---:|---:|
| Model calls | {b['calls']:,} | {t['calls']:,} |
| Total cost (USD) | ${b['cost_usd']:.6f} | ${t['cost_usd']:.6f} |
| **Cost saved** | | **{r['percent_saved']}%** |
| Average latency | {b['avg_latency_ms'] / 1000:.2f}s | {t['avg_latency_ms'] / 1000:.2f}s |
| Cache hit rate (exact + smart) | — | {t['cache_hit_rate']}% ({t['exact_hits']} + {t['semantic_hits']}) |
| Routed to cheap model | — | {t['routed_cheap_pct']}% |
| Errors | — | {t['errors']} |

**Quality:** on a random sample of {q['sample']} answers, {q['judge']} judged **{q['equal_or_better_pct']}%** of TokenSaver's answers
as good as or better than the strong model's ({q['distribution']}).

**Projection:** the same token counts priced as `{pj['strong']}` (strong) and `{pj['cheap']}` (cheap):
${pj['baseline_usd']:.4f} → ${pj['tokensaver_usd']:.4f} (**{pj['percent_saved']}% saved**).

![cost](cost.png) ![cache](cache.png) ![quality](quality.png)
"""
    (HERE / "results.md").write_text(md, encoding="utf-8")
    charts(r)


def charts(r: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.facecolor": "#0b0f14", "axes.facecolor": "#121821", "text.color": "#e6ebf2",
                         "axes.labelcolor": "#e6ebf2", "xtick.color": "#8b95a7", "ytick.color": "#8b95a7", "axes.edgecolor": "#222a36"})
    fig, ax = plt.subplots(figsize=(5, 3.4))
    ax.bar(["Strong only", "TokenSaver"], [r["baseline"]["cost_usd"], r["tokensaver"]["cost_usd"]], color=["#ffb547", "#3ddc97"])
    ax.set_title(f"Cost: {r['percent_saved']}% saved"); ax.set_ylabel("USD")
    fig.tight_layout(); fig.savefig(HERE / "cost.png", dpi=150); plt.close(fig)

    t = r["tokensaver"]
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    vals = [t["exact_hits"], t["semantic_hits"], t["calls"]]
    ax.pie(vals, labels=["exact hit", "smart hit", "model call"], colors=["#3ddc97", "#5ab0ff", "#a78bfa"], autopct="%1.0f%%",
           wedgeprops={"width": 0.45}, textprops={"color": "#e6ebf2"})
    ax.set_title("Where answers came from")
    fig.tight_layout(); fig.savefig(HERE / "cache.png", dpi=150); plt.close(fig)

    d = r["quality"]["distribution"]
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    ax.bar(list(d), list(d.values()), color=["#3ddc97", "#5ab0ff", "#ff6b6b"])
    ax.set_title(f"Quality: {r['quality']['equal_or_better_pct']}% equal or better")
    fig.tight_layout(); fig.savefig(HERE / "quality.png", dpi=150); plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--judge", type=int, default=100)
    args = ap.parse_args()
    s = Settings()
    s.router_mode = "classifier"
    prompts = load_prompts(args.limit)
    base = run_baseline(s, prompts)
    ts = run_tokensaver(s, prompts)
    quality = judge(s, prompts, base, ts, args.judge)
    report = summarize(s, prompts, base, ts, quality)
    write_report(report)
    print(json.dumps({k: report[k] for k in ("percent_saved", "baseline", "tokensaver", "quality", "projection")}, indent=1))


if __name__ == "__main__":
    main()
