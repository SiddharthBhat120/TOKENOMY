"""Use Tokenomy with the official `openai` library: only base_url changes.

    uvicorn tokenomy.app:app --port 8000      (in another terminal, from src/)
    python examples/client.py
"""
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed-for-ollama")

questions = [
    "How do I reset my password?",                       # miss -> model call
    "How do I reset my password?",                       # exact cache hit
    "I forgot my password, how can I reset it?",         # smart (semantic) cache hit
    "Design a refund system that is fast but resists fraud. Explain trade-offs step by step.",  # routed to strong model
]

for q in questions:
    raw = client.chat.completions.with_raw_response.create(
        model="tokenomy/auto", temperature=0, max_tokens=120,
        messages=[{"role": "user", "content": q}],
    )
    resp = raw.parse()
    h = raw.headers
    print(f"\n> {q}")
    print(f"  cache={h.get('x-tokenomy-cache-status')}  model={h.get('x-tokenomy-model')}  "
          f"route={h.get('x-tokenomy-route')}  cost=${float(h.get('x-tokenomy-cost-usd', 0)):.8f}")
    print("  " + resp.choices[0].message.content.strip().replace("\n", " ")[:160] + "…")
