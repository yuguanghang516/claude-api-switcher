"""安全、最小化的 Anthropic 兼容 API 连通性测试。"""
import re
import time
from urllib.parse import urlparse
from typing import Tuple

import requests


TEST_TIMEOUT = 15
GCLI2API_TEST_TIMEOUT = 90


class ApiTester:
    """每次测试只发送一个最小请求，不跟随重定向。"""

    @staticmethod
    def timeout_for(provider_kind: str) -> int:
        return (GCLI2API_TEST_TIMEOUT
                if str(provider_kind or "").strip().lower() == "gcli2api"
                else TEST_TIMEOUT)

    @staticmethod
    def _gcli_rate_limit_message(response) -> str:
        """Translate gcli2api's bounded quota error into an actionable message."""
        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = {}
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
            status = str(error.get("status") or "")
        else:
            detail = str(error)
            status = ""
        normalized = f"{status} {detail}".lower()
        exhausted = any(marker in normalized for marker in (
            "resource_exhausted", "exhausted your capacity", "quota", "capacity",
        ))
        match = re.search(
            r"(?:reset(?:s)?(?:\s+after|\s+in)?|恢复|重置)[^0-9]{0,12}"
            r"(?P<value>\d+\s*(?:d|h|m|s|天|小时|分钟|秒)(?:\s*\d+\s*(?:h|m|s|小时|分钟|秒))*)",
            detail, re.IGNORECASE,
        )
        reset = re.sub(r"\s+", "", match.group("value")) if match else ""
        if exhausted:
            suffix = f"；Google 提示约 {reset} 后恢复" if reset else ""
            return f"失败 · 当前模型额度已用完{suffix}；请刷新额度或切换其他模型"
        return "失败 · 429 当前请求受限；请稍后重试或切换模型"

    @staticmethod
    def test_provider(
        base_url: str,
        api_key: str,
        model: str,
        auth_mode: str = "bearer",
        provider_kind: str = "custom",
    ) -> Tuple[bool, str, int]:
        if not base_url:
            return False, "未设置 API Base URL / API Base URL not set", 0
        if not api_key:
            return False, "未设置 API Key / API Key not set", 0
        if not model:
            return False, "未设置模型名称 / Model name not set", 0

        parsed = urlparse(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False, "API 地址格式无效（需要完整的 http/https 地址）", 0
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False, "为保护 API Key，远程 API 地址必须使用 HTTPS", 0

        endpoint = base_url.strip().rstrip("/")
        if not endpoint.endswith("/v1/messages"):
            endpoint = f"{endpoint}/v1/messages"

        common_headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if auth_mode == "x-api-key":
            headers = {**common_headers, "x-api-key": api_key}
        else:
            headers = {**common_headers, "Authorization": f"Bearer {api_key}"}

        payload = {
            "model": model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "hi"}],
        }
        normalized_kind = str(provider_kind or "").strip().lower()
        request_timeout = ApiTester.timeout_for(normalized_kind)
        started = time.monotonic()
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=request_timeout,
                allow_redirects=False,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            status = response.status_code
            if status == 200:
                return True, f"正常 · {elapsed_ms}ms", elapsed_ms
            if 300 <= status < 400:
                return False, f"失败 · {status} 地址发生重定向（为保护 Key 已停止）", elapsed_ms
            if status == 401:
                return False, "失败 · 401 认证失败（检查 API Key 或认证方式）", elapsed_ms
            if status == 403:
                if normalized_kind == "gcli2api":
                    try:
                        detail = str(response.json()).lower()
                    except (ValueError, TypeError):
                        detail = response.text.lower()
                    if any(marker in detail for marker in (
                            "subscription_required", "#3501", "valid license")):
                        return False, (
                            "失败 · Google 通道需要许可证；个人用户请在 Gemini 反代页"
                            "切换为 Antigravity 后重新一键接入"
                        ), elapsed_ms
                    if any(marker in detail for marker in (
                            "密码错误", "invalid password", "api password")):
                        return False, (
                            "失败 · 本地 API 密码不匹配；请在 Gemini 反代页填写"
                            "服务启动时使用的 API_PASSWORD"
                        ), elapsed_ms
                    return False, (
                        "失败 · Google 凭证无权限；请打开 gcli2api 面板检查当前模式的登录状态"
                    ), elapsed_ms
                return False, "失败 · 403 无权限", elapsed_ms
            if status == 404:
                return False, "失败 · 404 API 地址或模型不存在", elapsed_ms
            if status == 429:
                if normalized_kind == "gcli2api":
                    return False, ApiTester._gcli_rate_limit_message(response), elapsed_ms
                return False, "失败 · 429 请求过于频繁或额度不足", elapsed_ms
            if status >= 500:
                return False, f"失败 · {status} 服务暂时不可用", elapsed_ms
            return False, f"失败 · HTTP {status}", elapsed_ms
        except requests.exceptions.Timeout:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if normalized_kind == "gcli2api":
                return False, (
                    f"失败 · gcli2api 在 {request_timeout} 秒内未完成凭证验证或模型切换；"
                    "请检查 7861/8787 服务和 gcli2api 日志"
                ), elapsed_ms
            return False, f"失败 · 超时（>{request_timeout}秒）", elapsed_ms
        except requests.exceptions.ConnectionError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            detail = str(exc).lower()
            if "getaddrinfo" in detail or "name resolution" in detail or "enotfound" in detail:
                return False, "失败 · 找不到服务器（检查 API 地址、网络或 DNS）", elapsed_ms
            return False, "失败 · 无法连接服务器（检查网络和 API 地址）", elapsed_ms
        except requests.exceptions.RequestException:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return False, "失败 · 请求异常（未泄露 API Key）", elapsed_ms
