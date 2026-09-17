import json
import sqlite3
import time

import pytest
import requests

from app.db_manager import DatabaseManager
from app.gateway_server import GatewayServer
from app.secret_storage import PREFIX, SecretProtectionError, protect_secret, unprotect_secret
from app.upstream_stream import relay_sse
from app.v2_config import V2ConfigManager


class Upstream:
    def __init__(self, status=200, body=b"{}", content_type="application/json", broken=False):
        self.status_code = status
        self.content = body
        self.headers = {"content-type": content_type}
        self.closed = False
        self.broken = broken

    def json(self):
        return json.loads(self.content)

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size=8192):
        # Deliberately split UTF-8 sequences and event boundaries.
        for i in range(0, len(self.content), 7):
            yield self.content[i:i+7]
        if self.broken:
            raise requests.ConnectionError("secret-test-do-not-leak")


@pytest.fixture
def gateway(tmp_path):
    db = DatabaseManager(str(tmp_path))
    assert db.add_provider({"id": "p", "name": "P", "base_url": "https://test.invalid/v1",
                            "api_key": "secret-test-do-not-leak"})[0]
    assert db.add_model({"id": "m", "model_name": "test", "provider_id": "p", "provider_name": "P"})[0]
    try:
        yield GatewayServer(db)
    finally:
        db.close()


def invoke(gateway, stream=False):
    return gateway.app.test_client().post("/v1/chat/completions", json={
        "model": "test", "messages": [{"role": "user", "content": "hi"}], "stream": stream})


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 302])
@pytest.mark.parametrize("stream", [False, True])
def test_upstream_errors_keep_status_and_hide_secrets(gateway, monkeypatch, status, stream):
    response = Upstream(status, b'{"error":"secret-test-do-not-leak"}')
    monkeypatch.setattr("app.gateway_server.requests.post", lambda *a, **kw: response)
    result = invoke(gateway, stream)
    assert result.status_code == (502 if status == 302 else status)
    assert "error" in result.get_json()
    assert b"secret-test" not in result.data
    log = gateway.db.get_recent_logs()[0]
    assert log["status"] == "error" and "secret-test" not in log["error"]
    assert response.closed


@pytest.mark.parametrize("body", [b"<html>login</html>", b"[]", b"null", b'{"choices":[]}', b'{"error":"oops"}'])
def test_fake_200_is_not_success(gateway, monkeypatch, body):
    response = Upstream(body=body)
    monkeypatch.setattr("app.gateway_server.requests.post", lambda *a, **kw: response)
    assert invoke(gateway).status_code == 502
    assert gateway.db.get_recent_logs()[0]["status"] == "error"
    assert response.closed


def test_stream_usage_and_redirect_policy(gateway, monkeypatch):
    body = ('data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}\n\n'
            'data: [DONE]\n\n').encode()
    upstream = Upstream(body=body, content_type="text/event-stream")
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return upstream
    monkeypatch.setattr("app.gateway_server.requests.post", post)
    result = invoke(gateway, True)
    assert b"[DONE]" in result.data
    assert "你好" in result.data.decode()
    log = gateway.db.get_recent_logs()[0]
    assert (log["input_tokens"], log["output_tokens"], log["total_tokens"], log["status"]) == (10, 5, 15, "success")
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["json"]["stream_options"]["include_usage"] is True
    assert upstream.closed


@pytest.mark.parametrize("body,broken", [(b'data: {"choices":[]}\n\n', False),
    (b'data: {"choices":[]}\n\n', True),
    (b'data: {"error":{"message":"secret-test-do-not-leak"}}\n\n', False),
    (b'data: invalid\n\n', False)])
def test_broken_stream_logs_failure_without_fabricated_done(gateway, monkeypatch, body, broken):
    upstream = Upstream(body=body, content_type="text/event-stream", broken=broken)
    monkeypatch.setattr("app.gateway_server.requests.post", lambda *a, **kw: upstream)
    result = invoke(gateway, True)
    assert b"event: error" in result.data
    assert b"secret-test" not in result.data and b"[DONE]" not in result.data
    assert gateway.db.get_recent_logs()[0]["status"] == "error"
    assert upstream.closed


def test_anthropic_url_auth_and_redaction(gateway, monkeypatch):
    gateway.db.update_provider("p", {"provider_type": "anthropic", "base_url": "https://test.invalid/anthropic",
                                     "auth_mode": "x-api-key"})
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Upstream(400, b'{"error":"secret-test-do-not-leak"}')
    monkeypatch.setattr("app.gateway_server.requests.post", post)
    result = invoke(gateway)
    assert result.status_code == 400 and b"secret-test" not in result.data
    assert calls[0][0] == "https://test.invalid/anthropic/v1/messages"
    assert calls[0][1]["headers"]["x-api-key"] == "secret-test-do-not-leak"
    assert calls[0][1]["allow_redirects"] is False


def test_anthropic_stream_usage_and_client_disconnect():
    body = (b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":12,"output_tokens":1}}}\n\n'
            b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":7}}\n\n'
            b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
    upstream = Upstream(body=body)
    logs = []
    assert "message_stop" in "".join(relay_sse(upstream, "anthropic", lambda *args: logs.append(args)))
    assert logs == [(12, 7, 19, "success", "")]
    upstream = Upstream(body=body)
    stream = relay_sse(upstream, "anthropic", lambda *args: logs.append(args))
    next(stream)
    stream.close()
    assert upstream.closed and logs[-1][3] == "error"


def test_secret_roundtrip_and_tamper():
    secret = "secret-test-中文"
    protected = protect_secret(secret)
    assert secret not in protected and protected.startswith(PREFIX)
    assert unprotect_secret(protected) == secret
    assert protect_secret("") == unprotect_secret("") == ""
    with pytest.raises(SecretProtectionError):
        unprotect_secret(PREFIX + "not-valid!!!")


def test_database_encrypted_writes_and_legacy_migration(tmp_path):
    db = DatabaseManager(str(tmp_path))
    assert db.add_provider({"id": "p", "name": "P", "api_key": "synthetic-old-key"})[0]
    assert db.get_provider("p")["api_key"] == "synthetic-old-key"
    conn = db._get_conn()
    assert conn.execute("SELECT api_key FROM providers").fetchone()[0].startswith(PREFIX)
    # Emulate a database produced by the old executable.
    conn.execute("UPDATE providers SET api_key='synthetic-legacy-key'")
    conn.commit()
    db.close()
    migrated = DatabaseManager(str(tmp_path))
    assert migrated.get_provider("p")["api_key"] == "synthetic-legacy-key"
    assert migrated.update_provider("p", {"api_key": "synthetic-new-key"})[0]
    assert migrated.get_all_providers()[0]["api_key"] == "synthetic-new-key"
    migrated.close()
    assert b"synthetic-legacy-key" not in (tmp_path / "gateway.db").read_bytes()
    assert b"synthetic-new-key" not in (tmp_path / "gateway.db").read_bytes()


def test_db_migration_failure_preserves_all_keys(tmp_path, monkeypatch):
    db = DatabaseManager(str(tmp_path))
    db.add_provider({"id": "p", "name": "P"})
    db._get_conn().execute("UPDATE providers SET api_key='legacy-key'")
    db._get_conn().commit()
    def fail(value):
        raise SecretProtectionError("failure")
    monkeypatch.setattr("app.db_manager.protect_secret", fail)
    with pytest.raises(SecretProtectionError):
        db._migrate_secrets()
    assert db._get_conn().execute("SELECT api_key FROM providers").fetchone()[0] == "legacy-key"
    db.close()


def test_multikey_migration_roundtrip_and_failed_save_preserves_file(tmp_path, monkeypatch):
    path = tmp_path / "v2_config.json"
    path.write_text(json.dumps({"multi_keys": {"p": ["synthetic-key"]}}), encoding="utf-8")
    config = V2ConfigManager(str(tmp_path))
    assert config.get_multi_keys("p") == ["synthetic-key"]
    original = path.read_bytes()
    assert b"synthetic-key" not in original
    assert V2ConfigManager(str(tmp_path)).get_multi_keys("p") == ["synthetic-key"]
    def fail(value):
        raise SecretProtectionError("failure")
    monkeypatch.setattr("app.v2_config.protect_secret", fail)
    assert config.set_multi_keys("p", ["new-key"]) is False
    assert path.read_bytes() == original and config.get_multi_keys("p") == ["synthetic-key"]


def test_unreadable_multikey_config_is_not_reset(tmp_path):
    path = tmp_path / "v2_config.json"
    original = json.dumps({"multi_keys": {"p": [PREFIX + "broken"]}})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(SecretProtectionError):
        V2ConfigManager(str(tmp_path))
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("body", [[], None, 1, "hello"])
def test_non_object_json_returns_400(gateway, body):
    result = gateway.app.test_client().post("/v1/chat/completions", data=json.dumps(body), content_type="application/json")
    assert result.status_code == 400
