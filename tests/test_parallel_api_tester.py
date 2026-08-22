"""Network-free regression tests for the API connection checker."""

import pytest
import requests

from app.api_tester import ApiTester
import app.api_tester as api_tester_module


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def _mock_post(monkeypatch, result):
    """Replace requests.post and return a list recording every attempted call."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(result, BaseException):
            raise result
        return _Response(result)

    monkeypatch.setattr(api_tester_module.requests, "post", fake_post)
    return calls


def test_success_is_reported_without_real_network(monkeypatch):
    calls = _mock_post(monkeypatch, 200)

    ok, message, elapsed_ms = ApiTester.test_provider(
        "https://unit.invalid/anthropic", "SENSITIVE_SENTINEL", "unit-model"
    )

    assert ok is True
    assert "正常" in message or "成功" in message
    assert elapsed_ms >= 0
    assert len(calls) == 1
    assert calls[0][0].endswith("/anthropic/v1/messages")


def test_dns_failure_has_actionable_message_without_real_network(monkeypatch):
    calls = _mock_post(
        monkeypatch,
        requests.exceptions.ConnectionError("getaddrinfo failed: ENOTFOUND"),
    )

    ok, message, _ = ApiTester.test_provider(
        "https://unit.invalid/anthropic", "SENSITIVE_SENTINEL", "unit-model"
    )

    assert ok is False
    assert any(word in message for word in ("找不到", "DNS", "无法连接", "地址无效"))
    assert len(calls) >= 1


def test_timeout_has_actionable_message_without_real_network(monkeypatch):
    calls = _mock_post(monkeypatch, requests.exceptions.Timeout("unit timeout"))

    ok, message, _ = ApiTester.test_provider(
        "https://unit.invalid/anthropic", "SENSITIVE_SENTINEL", "unit-model"
    )

    assert ok is False
    assert "超时" in message
    assert len(calls) == 1


def test_timeout_is_provider_specific(monkeypatch):
    calls = _mock_post(monkeypatch, 200)
    ApiTester.test_provider(
        "https://unit.invalid/anthropic", "SENSITIVE_SENTINEL", "unit-model",
        provider_kind="custom")
    ApiTester.test_provider(
        "http://127.0.0.1:8787", "SENSITIVE_SENTINEL", "gemini-model",
        auth_mode="x-api-key", provider_kind="gcli2api")

    assert calls[0][1]["timeout"] == 15
    assert calls[1][1]["timeout"] == 90


def test_gcli_timeout_names_the_real_stage_and_limit(monkeypatch):
    calls = _mock_post(monkeypatch, requests.exceptions.Timeout("unit timeout"))
    ok, message, _ = ApiTester.test_provider(
        "http://127.0.0.1:8787", "SENSITIVE_SENTINEL", "gemini-model",
        auth_mode="x-api-key", provider_kind="gcli2api")

    assert not ok
    assert "90 秒" in message
    assert "凭证验证或模型切换" in message
    assert calls[0][1]["timeout"] == 90


@pytest.mark.parametrize(
    ("status", "expected_words"),
    [
        (401, ("401", "认证", "Key")),
        (403, ("403", "权限")),
        (404, ("404", "地址", "模型")),
        (429, ("429", "频繁", "额度")),
        (503, ("503", "服务")),
    ],
)
def test_http_failures_are_mapped_without_real_network(
    monkeypatch, status, expected_words
):
    calls = _mock_post(monkeypatch, status)

    ok, message, elapsed_ms = ApiTester.test_provider(
        "https://unit.invalid/anthropic", "SENSITIVE_SENTINEL", "unit-model"
    )

    assert ok is False
    assert any(word in message for word in expected_words)
    assert elapsed_ms >= 0
    assert len(calls) >= 1


def test_auth_failure_sends_only_one_minimal_request(monkeypatch):
    calls = _mock_post(monkeypatch, 401)

    ApiTester.test_provider(
        "https://unit.invalid/anthropic", "SENSITIVE_SENTINEL", "unit-model"
    )

    assert len(calls) == 1
