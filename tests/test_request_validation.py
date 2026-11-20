import pytest
from app.gateway_server import GatewayServer
from app.upstream_stream import relay_sse


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize("change", [
    {"model": ["invalid"]}, {"model": {}}, {"model": "  "},
    {"stream": "false"}, {"stream": 1}, {"messages": "hello"},
    {"messages": [1]}, {"max_tokens": True}, {"max_tokens": -1},
])
def test_invalid_request_rejected_before_routing(route, change, monkeypatch):
    gateway = GatewayServer()
    gateway.configure_gcli_failover("http://127.0.0.1:7861", "test-key", ["gemini-pro"])
    def unexpected(*a, **kw):
        pytest.fail("Invalid request reached upstream")
    monkeypatch.setattr(gateway.gcli_failover, "forward", unexpected)
    body = {"model": "test", "messages": [{"role": "user", "content": "hi"}]}
    body.update(change)
    result = gateway.app.test_client().post(route, json=body, headers={"x-api-key": "test-key"})
    assert result.status_code == 400
    assert result.get_json()["error"]["type"] == "invalid_request_error"


def test_close_failure_does_not_lose_usage():
    class Response:
        def iter_content(self, **kwargs):
            yield b'data: {"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\ndata: [DONE]\n\n'
        def close(self):
            raise OSError("socket close failure")
    records = []
    with pytest.raises(OSError):
        list(relay_sse(Response(), "openai", lambda *args: records.append(args)))
    assert records == [(3, 2, 5, "success", "")]
