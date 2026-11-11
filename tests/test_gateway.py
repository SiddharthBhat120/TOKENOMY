import time

from conftest import chat

from tokenomy.cache import cache_key, is_cacheable
from tokenomy.pricing import PriceBook
from tokenomy.router import RuleScorer


# ---------------- Phase 1: proxy ----------------
def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_proxy_forwards_and_returns_openai_shape(client, upstream):
    r = client.post("/v1/chat/completions", json=chat())
    assert r.status_code == 200
    data = r.json()
    assert data["choices"][0]["message"]["content"] == "answer to: What is the capital of India?"
    assert data["model"] == "ollama/gemma3:12b"
    assert upstream.calls[0]["url"].startswith("http://localhost:11434/v1")
    assert upstream.calls[0]["body"]["model"] == "gemma3:12b"  # "ollama/" prefix stripped


def test_openrouter_gets_auth_header(client, upstream):
    client.post("/v1/chat/completions", json=chat(model="meta-llama/llama-3.2-3b-instruct:free"))
    assert upstream.calls[0]["url"].startswith("https://openrouter.ai/api/v1")
    assert upstream.calls[0]["headers"]["authorization"] == "Bearer test-key"


def test_missing_openrouter_key_gives_401(make_client):
    with make_client(openrouter_api_key="") as c:
        r = c.post("/v1/chat/completions", json=chat(model="openai/gpt-4o-mini"))
    assert r.status_code == 401
    assert "OPENROUTER_API_KEY" in r.json()["error"]["message"]


def test_upstream_error_maps_to_502(client, upstream):
    upstream.fail_models.add("gemma3:12b")
    r = client.post("/v1/chat/completions", json=chat())
    assert r.status_code == 502
    assert r.json()["error"]["type"] == "upstream_error"


def test_bad_request_rejected(client):
    assert client.post("/v1/chat/completions", json={"model": "x", "messages": []}).status_code == 400


def test_stream_returns_sse(client):
    r = client.post("/v1/chat/completions", json=chat(stream=True))
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "data: [DONE]" in r.text


# ---------------- Phase 2: cost tracking ----------------
def test_cost_calculation():
    prices = PriceBook()
    # gpt-4o: $2.50 in / $10 out per 1M tokens
    assert abs(prices.cost("openai/gpt-4o", 1_000_000, 1_000_000) - 12.5) < 1e-9
    assert prices.cost("unknown/model", 1000, 1000) == 0.0
    assert prices.known("ollama/gemma3:12b")  # priced as its hosted twin


def test_stats_counts_requests_and_savings(client):
    client.post("/v1/chat/completions", json=chat())
    client.post("/v1/chat/completions", json=chat())  # exact hit
    s = client.get("/stats").json()
    assert s["requests"] == 2 and s["exact_hits"] == 1
    assert s["money_saved_usd"] > 0
    assert s["cache_hit_rate"] == 50.0


# ---------------- Phase 3: exact cache ----------------
def test_exact_cache_hit(client, upstream):
    a = client.post("/v1/chat/completions", json=chat())
    b = client.post("/v1/chat/completions", json=chat())
    assert a.headers["X-Tokenomy-Cache-Status"] == "miss"
    assert b.headers["X-Tokenomy-Cache-Status"] == "exact_hit"
    assert b.json()["x_tokenomy"]["cost_usd"] == 0
    assert len(upstream.calls) == 1


def test_exact_cache_miss_on_different_prompt(client, upstream):
    client.post("/v1/chat/completions", json=chat(content="Translate hello to Hindi"))
    r = client.post("/v1/chat/completions", json=chat(content="Write a haiku about the monsoon in Mumbai"))
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"
    assert len(upstream.calls) == 2


def test_high_temperature_not_cached(client, upstream):
    client.post("/v1/chat/completions", json=chat(temperature=0.9))
    r = client.post("/v1/chat/completions", json=chat(temperature=0.9))
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"
    assert len(upstream.calls) == 2


def test_skip_header_bypasses_cache(client, upstream):
    client.post("/v1/chat/completions", json=chat())
    r = client.post("/v1/chat/completions", json=chat(), headers={"X-Tokenomy-Cache": "skip"})
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"
    assert len(upstream.calls) == 2


def test_ttl_expiry(make_client, upstream):
    with make_client(cache_ttl_seconds=1, semantic_enabled=False) as c:
        c.post("/v1/chat/completions", json=chat())
        time.sleep(1.2)
        r = c.post("/v1/chat/completions", json=chat())
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"


def test_key_ignores_whitespace_but_not_params():
    a = {"messages": [{"role": "user", "content": "hello   world"}], "temperature": 0}
    b = {"messages": [{"role": "user", "content": "hello world"}], "temperature": 0}
    c = {"messages": [{"role": "user", "content": "hello world"}], "temperature": 0.2}
    assert cache_key("m", a) == cache_key("m", b) != cache_key("m", c)
    assert is_cacheable({"temperature": 0.3}, 0.3) and not is_cacheable({}, 0.3)  # default temp 1.0


# ---------------- Phase 4: semantic cache ----------------
def test_semantic_hit_on_paraphrase(client, upstream):
    client.post("/v1/chat/completions", json=chat(content="What is the capital of India?"))
    r = client.post("/v1/chat/completions", json=chat(content="what is the capital of india"))
    # exact key differs (case/punctuation) but meaning is the same
    assert r.headers["X-Tokenomy-Cache-Status"] == "semantic_hit"
    assert float(r.headers["X-Tokenomy-Similarity"]) >= 0.85
    assert len(upstream.calls) == 1


def test_semantic_threshold_protects_different_meaning(make_client, upstream):
    with make_client(semantic_threshold=0.99) as c:
        c.post("/v1/chat/completions", json=chat(content="cheap flights to Delhi from Mumbai"))
        r = c.post("/v1/chat/completions", json=chat(content="cheap flights from Delhi to Goa"))
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"


def test_semantic_scoped_by_model(client, upstream):
    client.post("/v1/chat/completions", json=chat(model="ollama/gemma3:12b"))
    r = client.post("/v1/chat/completions", json=chat(model="ollama/gemma3:4b", content="what is the capital of india"))
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"


def test_semantic_skips_long_conversations(client, upstream):
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "What is the capital of India?"}]
    client.post("/v1/chat/completions", json={"model": "ollama/gemma3:12b", "messages": msgs, "temperature": 0})
    r = client.post("/v1/chat/completions", json={"model": "ollama/gemma3:12b", "temperature": 0,
                                                  "messages": msgs[:2] + [{"role": "user", "content": "capital of india?"}]})
    assert r.headers["X-Tokenomy-Cache-Status"] == "miss"


# ---------------- Phase 5: router ----------------
def test_rules_route_easy_and_hard():
    r = RuleScorer()
    assert r.decide("Translate hello to Hindi").tier == "easy"
    assert r.decide("Design a scalable architecture and analyze the trade-offs step by step").tier == "hard"
    assert r.decide("```python\ndef f(x):\n    return x\n```\nDebug this and optimize it").tier == "hard"


def test_auto_model_routes_and_reports(client, upstream):
    easy = client.post("/v1/chat/completions", json=chat(model="tokenomy/auto", content="Translate hello to Hindi"))
    hard = client.post("/v1/chat/completions", json=chat(model="tokenomy/auto",
                                                         content="Design a database schema and analyze trade-offs step by step"))
    assert easy.headers["X-Tokenomy-Route"] == "easy"
    assert easy.headers["X-Tokenomy-Model"] == "ollama/gemma3:4b"
    assert hard.headers["X-Tokenomy-Model"] == "ollama/gemma3:12b"
    # baseline for auto = strong model, so the easy request saved money
    x = easy.json()["x_tokenomy"]
    assert x["cost_without_tokenomy_usd"] > x["cost_usd"] > 0


def test_fallback_to_strong_when_cheap_fails(client, upstream):
    upstream.fail_models.add("gemma3:4b")
    r = client.post("/v1/chat/completions", json=chat(model="tokenomy/auto", content="Translate hello to Hindi"))
    assert r.status_code == 200
    assert r.headers["X-Tokenomy-Fallback"] == "true"
    assert r.headers["X-Tokenomy-Model"] == "ollama/gemma3:12b"


# ---------------- Phase 6: dashboard endpoints ----------------
def test_dashboard_endpoints(client):
    client.post("/v1/chat/completions", json=chat())
    assert client.get("/stats/timeseries?bucket=minute").json()[0]["requests"] == 1
    assert client.get("/stats/models").json()[0]["model"] == "ollama/gemma3:12b"
    assert client.get("/requests?limit=5").json()["total"] == 1
    assert client.get("/router/explain", params={"prompt": "hi"}).json()["tier"] == "easy"
    assert client.post("/admin/reset").json()["ok"]
    assert client.get("/stats").json()["requests"] == 0


# ---------------- key-facts guard (why threshold alone is not enough) ----------------
def test_guard_blocks_look_alike_prompts():
    from tokenomy.semantic import same_key_facts
    assert not same_key_facts("Flights to Delhi from Mumbai", "Flights from Delhi to Mumbai")  # cosine 0.99!
    assert not same_key_facts("Is the store open on Sunday?", "Is the store open on Monday?")
    assert not same_key_facts("Best laptop under 50000 rupees", "Best laptop under 80000 rupees")
    assert not same_key_facts("Translate hello to Hindi", "Translate hello to Tamil")
    assert not same_key_facts("How do I cancel my order?", "How do I place an order?")
    assert not same_key_facts("Is this covered by warranty?", "Is this not covered by warranty?")


def test_guard_allows_real_paraphrases():
    from tokenomy.semantic import same_key_facts
    assert same_key_facts("What's the capital of India?", "India's capital city?")
    assert same_key_facts("How do I reset my password?", "I forgot my password, how can I reset it?")
    assert same_key_facts("Can I cancel my order?", "Is it possible to cancel an order I placed?")
