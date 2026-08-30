from types import SimpleNamespace

import pytest
import requests

from app.gcli_failover import GcliModelFailover
from app.gateway_server import GatewayServer


class FakeResponse:
    def __init__(self, status_code, body=b"{}", content_type="application/json"):
        self.status_code = status_code
        self.content = body
        self.headers = {"content-type": content_type}
        self.closed = False

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size=8192):
        yield self.content


def test_429_cools_model_and_switches_to_next_candidate(monkeypatch):
    now = [100.0]
    router = GcliModelFailover(clock=lambda: now[0])
    router.configure(
        "http://127.0.0.1:7861/antigravity", "secret",
        ["gemini-pro", "claude-sonnet"],
        {"gemini-pro": 100, "claude-sonnet": 80}, preferred_model="gemini-pro")
    responses = iter((FakeResponse(429), FakeResponse(200, b'{"content":[]}')))
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    monkeypatch.setattr("app.gcli_failover.requests.post", fake_post)
    response, used_model = router.forward({"model": "gemini-pro", "messages": [{"role": "user"}]})

    assert response.status_code == 200
    assert used_model == "claude-sonnet"
    assert [call[1]["json"]["model"] for call in calls] == ["gemini-pro", "claude-sonnet"]
    assert router.status()["models"][0]["cooldown_seconds"] == 60
    assert router.status()["last_event"].to_model == "claude-sonnet"


def test_candidates_prefer_same_model_family_before_cross_family():
    router = GcliModelFailover()
    router.configure(
        "http://127.0.0.1:7861/antigravity", "secret",
        ["gemini-pro", "claude-sonnet", "gemini-flash"],
        {"gemini-pro": 100, "claude-sonnet": 100, "gemini-flash": 100},
        preferred_model="gemini-pro")
    assert router.candidates("gemini-pro") == [
        "gemini-pro", "gemini-flash", "claude-sonnet"]


def test_authentication_error_is_not_hidden_by_model_switch(monkeypatch):
    router = GcliModelFailover()
    router.configure("http://127.0.0.1:7861/antigravity", "secret", ["gemini-a", "gemini-b"])
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"]["model"])
        return FakeResponse(403)

    monkeypatch.setattr("app.gcli_failover.requests.post", fake_post)
    response, model = router.forward({"model": "gemini-a", "messages": [{}]})
    assert response.status_code == 403 and model == "gemini-a"
    assert calls == ["gemini-a"]


def test_streaming_429_switches_before_any_bytes_are_exposed(monkeypatch):
    router = GcliModelFailover()
    router.configure("http://127.0.0.1:7861/antigravity", "secret", ["gemini-a", "gemini-b"])
    first = FakeResponse(429, b"rate limited")
    second = FakeResponse(200, b"data: ok\n\n", "text/event-stream")
    responses = iter((first, second))
    monkeypatch.setattr(
        "app.gcli_failover.requests.post", lambda *args, **kwargs: next(responses))

    response, model = router.forward({"model": "gemini-a", "messages": [{}], "stream": True}, stream=True)
    assert first.closed
    assert response is second and model == "gemini-b"


def test_failover_enforces_total_time_budget(monkeypatch):
    now = [100.0]
    router = GcliModelFailover(timeout=45, total_timeout=70, clock=lambda: now[0])
    router.configure(
        "http://127.0.0.1:7861/antigravity", "secret",
        ["gemini-a", "gemini-b", "gemini-c"])
    timeouts = []

    def fake_post(*_args, **kwargs):
        timeouts.append(kwargs["timeout"])
        now[0] += 40
        return FakeResponse(429)

    monkeypatch.setattr("app.gcli_failover.requests.post", fake_post)
    response, used_model = router.forward({"model": "gemini-a", "messages": [{}]})

    assert response.status_code == 429
    assert used_model == "gemini-b"
    assert timeouts == [45, 30]


def test_failover_switches_after_timeout_while_budget_remains(monkeypatch):
    now = [10.0]
    router = GcliModelFailover(timeout=30, total_timeout=60, clock=lambda: now[0])
    router.configure(
        "http://127.0.0.1:7861/antigravity", "secret",
        ["gemini-a", "claude-b"])
    calls = []

    def fake_post(*_args, **kwargs):
        calls.append(kwargs["json"]["model"])
        if len(calls) == 1:
            now[0] += 20
            raise requests.exceptions.Timeout()
        return FakeResponse(200)

    monkeypatch.setattr("app.gcli_failover.requests.post", fake_post)
    response, used_model = router.forward({"model": "gemini-a", "messages": [{}]})

    assert response.status_code == 200
    assert used_model == "claude-b"
    assert calls == ["gemini-a", "claude-b"]


def test_gateway_anthropic_route_requires_key_and_passes_upstream_body(monkeypatch):
    gateway = GatewayServer(host="127.0.0.1", port=18788)
    gateway.configure_gcli_failover(
        "http://127.0.0.1:7861/antigravity", "secret", ["gemini-pro"],
        {"gemini-pro": 100}, "gemini-pro")
    upstream = FakeResponse(
        200, b'{"id":"msg_test","content":[{"type":"text","text":"ok"}],"usage":{}}')
    monkeypatch.setattr(gateway.gcli_failover, "forward", lambda payload, stream=False: (upstream, "gemini-pro"))
    client = gateway.app.test_client()

    unauthorized = client.post("/v1/messages", json={"model": "gemini-pro", "messages": [{}]})
    assert unauthorized.status_code == 401
    response = client.post(
        "/v1/messages", headers={"x-api-key": "secret"},
        json={"model": "gemini-pro", "messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 200
    assert response.headers["X-Gcli-Model-Used"] == "gemini-pro"
    assert response.get_json()["id"] == "msg_test"
