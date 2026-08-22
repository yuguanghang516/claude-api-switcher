from types import SimpleNamespace

import pytest
import requests

from app.balance_checker import BalanceChecker
from app.db_manager import DatabaseManager


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ({"name": "LongCat", "base_url": "https://api.longcat.chat/anthropic"}, "longcat"),
        ({"name": "Gemini CLI", "provider_kind": "gcli2api", "base_url": "http://127.0.0.1:7861"}, "gcli2api"),
        ({"name": "DeepSeek", "base_url": "https://api.deepseek.com"}, "deepseek"),
        ({"name": "Custom", "base_url": "https://example.com"}, "custom"),
    ],
)
def test_provider_type_is_inferred_from_bounded_metadata(provider, expected):
    assert BalanceChecker.infer_provider_type(provider) == expected


def test_longcat_is_explicitly_unsupported_instead_of_fake_balance(monkeypatch):
    monkeypatch.setattr("app.balance_checker.requests.get", lambda *_a, **_k: pytest.fail("must not probe"))
    result = BalanceChecker().check_balance(
        "longcat", "secret", "https://api.longcat.chat/anthropic", "LongCat")
    assert result.status == "unsupported"
    assert result.supports_balance is False
    assert result.percent_remaining == -1
    assert "未提供账户余额 API" in result.error
    assert result.portal_url == "https://longcat.chat/platform/"


def test_openai_no_longer_uses_legacy_credit_summary(monkeypatch):
    monkeypatch.setattr("app.balance_checker.requests.get", lambda *_a, **_k: pytest.fail("must not probe"))
    result = BalanceChecker().check_balance("openai", "secret", provider_name="OpenAI")
    assert result.status == "unsupported"
    assert "旧版账单端点" in result.error


def test_deepseek_uses_fixed_official_endpoint_without_redirects(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "12.34"}]}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr("app.balance_checker.requests.get", fake_get)
    result = BalanceChecker().check_balance("deepseek", "secret", provider_name="DeepSeek")
    assert result.status == "official"
    assert result.balance == 12.34
    assert result.currency == "CNY"
    assert seen["url"] == "https://api.deepseek.com/user/balance"
    assert seen["allow_redirects"] is False


def test_deepseek_timeout_does_not_expose_exception(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise requests.exceptions.Timeout("Bearer secret")

    monkeypatch.setattr("app.balance_checker.requests.get", timeout)
    result = BalanceChecker().check_balance("deepseek", "secret", provider_name="DeepSeek")
    assert result.status == "error"
    assert "secret" not in result.error


def test_gateway_usage_is_grouped_by_real_provider_without_guessing_history(tmp_path):
    db = DatabaseManager(str(tmp_path))
    db.log_request({
        "provider": "LongCat", "model": "LongCat-2.0", "status": "success",
        "input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
    })
    db.log_request({
        "provider": "", "model": "legacy-model", "status": "error",
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
    })

    overview = db.get_provider_usage_overview()
    rows = {item["provider"]: item for item in overview["today"]}

    assert rows["LongCat"]["total_requests"] == 1
    assert rows["LongCat"]["total_tokens"] == 120
    assert rows["历史记录未标注"]["failed_requests"] == 1
