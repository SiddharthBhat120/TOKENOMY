import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tokenomy.app import create_app  # noqa: E402
from tokenomy.config import Settings  # noqa: E402
from tokenomy.embeddings import HashEmbedder  # noqa: E402


class FakeUpstream:
    """Pretends to be Ollama/OpenRouter. Records calls; can be told to fail."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail_models: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        self.calls.append({"url": str(request.url), "body": body, "headers": dict(request.headers)})
        if body["model"] in self.fail_models:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        question = body["messages"][-1]["content"]
        return httpx.Response(200, json={
            "id": f"chatcmpl-{len(self.calls)}", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"answer to: {question}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        })


@pytest.fixture
def upstream():
    return FakeUpstream()


@pytest.fixture
def make_client(tmp_path, upstream):
    def _make(**overrides) -> TestClient:
        s = Settings()
        s.db_path = str(tmp_path / "test.db")
        s.openrouter_api_key = "test-key"
        s.router_mode = "rules"
        s.semantic_threshold = 0.85
        for k, v in overrides.items():
            setattr(s, k, v)
        app = create_app(s, embedder=HashEmbedder(), transport=httpx.MockTransport(upstream))
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


def chat(model="ollama/gemma3:12b", content="What is the capital of India?", temperature=0.0, **extra):
    return {"model": model, "messages": [{"role": "user", "content": content}], "temperature": temperature, **extra}
