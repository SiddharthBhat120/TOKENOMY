# Tokenomy: explain it in an interview

## 30-second pitch
"Companies pay for every LLM call, but many requests are repeats, paraphrases, or easy questions sent
to an expensive model. Tokenomy is a drop-in gateway: you change one line, the `base_url`, and it
answers repeats from an exact cache, paraphrases from a semantic cache, and routes easy prompts to a
cheaper model. A dashboard shows exactly how much money it saved, and a 1,000-prompt benchmark proves
it without hurting answer quality."

## How a request flows (gateway.py)
1. **Exact cache**: SHA-256 of (model, normalised messages, temperature, other params). Hit = return stored answer, cost 0.
2. **Semantic cache**: embed the last user message with MiniLM, cosine search inside the same (model, system prompt) scope;
   reuse only if similarity ≥ threshold **and** the key-facts guard agrees.
3. **Router** (model = `tokenomy/auto`): classifier says EASY → cheap model, HARD → strong model. If the cheap model errors, retry on strong.
4. **Provider**: `ollama/...` → local Ollama, anything else → OpenRouter. Same OpenAI format both ways.
5. **Log**: tokens, real cost, and "cost without Tokenomy" (strong-model price) → savings.

## 10 questions you will probably get

**1. Why only cache low-temperature requests?**
Temperature controls randomness. At high temperature the caller *wants* different answers each time
(brainstorming, creative text). Replaying one stored answer would silently break that. At ≤ 0.3 the
model is near-deterministic, so a cached answer is what they'd get anyway. OpenAI's default is 1.0,
so a request with no temperature is *not* cached; that's the safe default.

**2. How did you choose the semantic threshold? What goes wrong if it's too low?**
I ran `scripts/tune_threshold.py` on pairs that mean the same and pairs that only *look* the same.
Too low means wrong answers (a different question gets someone else's answer). Too high means almost no hits.
The surprise: "flights **to** Delhi **from** Mumbai" vs "flights **from** Delhi **to** Mumbai" scored
**0.99**, higher than real paraphrases. No threshold can fix that, so I added a key-facts guard (numbers,
dates/days, proper nouns, to/from direction, opposite verbs like cancel/place). With the guard, wrong hits went
from 2/8 to 0/8 and I could lower the threshold to 0.85 to catch more real paraphrases.

**3. How does the router decide easy vs hard? What if it's wrong?**
v1 was rules (length, code, maths, words like "design/prove/step by step"): 68% accurate on a held-out split.
v2 embeds the prompt and runs logistic regression trained on 300 labelled prompts: 96% on the held-out split.
I blend 75% classifier + 25% rules so obvious code/maths is never sent cheap. If it wrongly sends a hard
prompt to the cheap model, the answer may be weaker; the benchmark's quality judge measures exactly that.
If the cheap model *fails*, there's an automatic fallback to the strong model.

**4. How do you know quality didn't drop?**
LLM-as-judge: the strong model compares Tokenomy's answer with the strong model's own answer, blind and
in random order (to avoid position bias), on a random sample. I report the % judged equal or better.
Limitation: a judge model can be biased; a human spot-check of the sample is the next step.

**5. Why is the cache scoped by model and system prompt?**
The same question can need a different answer under a different persona ("you are a lawyer" vs "you are
a support bot") or model. Mixing them would leak answers across contexts.

**6. Why only single-turn conversations for the semantic cache?**
In a long chat, "and what about the second one?" depends on earlier messages. The last message alone
doesn't carry the meaning, so semantic matching would be unsafe. Exact caching still works because the
whole conversation is in the key.

**7. How would you scale to 10,000 requests/second?**
Run many stateless gateway workers behind a load balancer; move the exact cache to Redis; move embeddings
to a vector DB (pgvector, Qdrant) or FAISS with sharding; batch embedding calls; log asynchronously
(queue → ClickHouse/Postgres); and keep the router model in memory (it's tiny).

**8. Privacy: you're storing users' prompts.**
Add a TTL (already there), per-tenant cache scopes, a "never cache" header (`X-Tokenomy-Cache: skip`),
PII redaction before caching, encryption at rest, and an opt-out for sensitive endpoints.

**9. How do you compute savings honestly?**
For every request I log the real cost and what it *would* cost if sent to the strong model (same token
counts). Prices come from OpenRouter's public API (`scripts/update_pricing.py`), not made-up numbers.
Local Ollama models are priced at the hosted price of the same open-weights model.

**10. What would you improve next?**
Streaming pass-through for cache misses, per-tenant budgets and alerts, a vector DB, a learned threshold per
intent, and human evaluation of the quality sample.

## 60-second demo script
1. (0–10s) "This is Tokenomy, a gateway that cuts LLM bills." Show the dashboard receipt.
2. (10–25s) Playground: send "How do I reset my password?" → **miss**, show cost and latency.
   Send it again → **exact hit**, $0, ~5 ms.
3. (25–40s) Send "I forgot my password, how can I reset it?" → **smart hit**, show similarity.
   Send the trap "How do I reset my username?" → **miss**: the guard protected the user.
4. (40–50s) Type a design question: the router panel flips to HARD → strong model.
5. (50–60s) Benchmark tab: "% cheaper on 1,000 prompts, with quality checked by a judge model."
