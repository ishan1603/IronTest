"""Failover behaviour across free-tier providers.

Rate limiting is the normal steady state on free tiers, so the chain must treat
an exhausted provider as routine and move on rather than ending the run.
"""

import json

import pytest

from llm import client as llm_client
from llm.client import LLMError, NoProviderConfigured, generate_json

ALL_KEYS = ["GROQ_API_KEY", "GEMINI_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY"]


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload or {})
        self.headers = headers or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def completion(content: str) -> FakeResponse:
    return FakeResponse(payload={"choices": [{"message": {"content": content}}]})


def rate_limited() -> FakeResponse:
    return FakeResponse(status_code=429, payload={"error": {"message": "rate limit exceeded"}})


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start every test with no provider keys and no sleeping."""
    for key in ALL_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("LLM_PROVIDER_ORDER", raising=False)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)


@pytest.fixture
def calls(monkeypatch):
    """Record every outbound request and serve queued responses."""
    recorded: list[dict] = []
    queue: list[FakeResponse] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        recorded.append({"url": url, "model": (json or {}).get("model"), "body": json})
        return queue.pop(0) if queue else completion('{"ok": true}')

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    recorded_queue = (recorded, queue)
    return recorded_queue


def test_raises_when_no_provider_is_configured():
    with pytest.raises(NoProviderConfigured) as exc:
        generate_json(system_prompt="s", user_prompt="u")
    assert "GROQ_API_KEY" in str(exc.value)


def test_uses_first_configured_provider(monkeypatch, calls):
    recorded, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    queue.append(completion('{"intent": "works"}'))

    assert generate_json(system_prompt="s", user_prompt="u") == {"intent": "works"}
    assert len(recorded) == 1
    assert "api.groq.com" in recorded[0]["url"]


def test_falls_through_to_next_provider_when_rate_limited(monkeypatch, calls):
    """A 429 on every Groq model must hand off to Gemini, not end the run."""
    recorded, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODELS", "m1,m2")
    monkeypatch.setenv("GEMINI_MODELS", "g1")

    # Both Groq models exhaust their retries, then Gemini answers.
    for _ in range(6):
        queue.append(rate_limited())
    queue.append(completion('{"served_by": "gemini"}'))

    assert generate_json(system_prompt="s", user_prompt="u") == {"served_by": "gemini"}
    assert "generativelanguage" in recorded[-1]["url"]


def test_tries_each_model_within_a_provider(monkeypatch, calls):
    recorded, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODELS", "first,second")

    queue.append(FakeResponse(status_code=404, payload={"error": {"message": "model not found"}}))
    queue.append(completion('{"model": "second"}'))

    assert generate_json(system_prompt="s", user_prompt="u") == {"model": "second"}
    assert [c["model"] for c in recorded] == ["first", "second"]


def test_provider_order_is_configurable(monkeypatch, calls):
    recorded, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDER_ORDER", "openrouter,groq")
    queue.append(completion('{"ok": true}'))

    generate_json(system_prompt="s", user_prompt="u")
    assert "openrouter.ai" in recorded[0]["url"]


def test_unconfigured_providers_are_never_called(monkeypatch, calls):
    recorded, queue = calls
    monkeypatch.setenv("CEREBRAS_API_KEY", "k")
    queue.append(completion('{"ok": true}'))

    generate_json(system_prompt="s", user_prompt="u")
    assert all("cerebras.ai" in c["url"] for c in recorded)


def test_retries_prompt_repair_before_abandoning_model(monkeypatch, calls):
    """Unparseable output earns a stricter re-ask on the same model."""
    recorded, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODELS", "only")

    queue.append(completion("Sure! Here you go: not json at all"))
    queue.append(completion('{"recovered": true}'))

    assert generate_json(system_prompt="s", user_prompt="u") == {"recovered": True}
    assert len(recorded) == 2

    # First ask is clean; the retry escalates to an explicit JSON-only instruction.
    first, second = (c["body"]["messages"][1]["content"] for c in recorded)
    assert first == "u"
    assert "Return ONLY a valid JSON object" in second


def test_recovers_json_from_markdown_fences(monkeypatch, calls):
    _, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    queue.append(completion('```json\n{"fenced": true}\n```'))

    assert generate_json(system_prompt="s", user_prompt="u") == {"fenced": True}


def test_exhausting_every_provider_raises_with_diagnostics(monkeypatch, calls):
    _, queue = calls
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODELS", "only")
    for _ in range(3):
        queue.append(rate_limited())

    with pytest.raises(LLMError) as exc:
        generate_json(system_prompt="s", user_prompt="u")

    assert "groq/only" in str(exc.value)
    assert exc.value.attempts


def test_openrouter_receives_attribution_headers(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(headers or {})
        return completion('{"ok": true}')

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    generate_json(system_prompt="s", user_prompt="u")
    assert "HTTP-Referer" in captured
    assert captured["X-Title"]
