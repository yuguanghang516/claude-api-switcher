"""安全、最小化的 Anthropic 兼容 API 连通性测试。"""
import time
from urllib.parse import urlparse
from typing import Tuple

import requests


TEST_TIMEOUT = 15


class ApiTester:
    """每次测试只发送一个最小请求，不跟随重定向。"""

    @staticmethod
    def test_provider(
        base_url: str,
        api_key: str,
        model: str,
        auth_mode: str = "bearer",
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
        started = time.monotonic()
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=TEST_TIMEOUT,
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
                return False, "失败 · 403 无权限", elapsed_ms
            if status == 404:
                return False, "失败 · 404 API 地址或模型不存在", elapsed_ms
            if status == 429:
                return False, "失败 · 429 请求过于频繁或额度不足", elapsed_ms
            if status >= 500:
                return False, f"失败 · {status} 服务暂时不可用", elapsed_ms
            return False, f"失败 · HTTP {status}", elapsed_ms
        except requests.exceptions.Timeout:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return False, f"失败 · 超时（>{TEST_TIMEOUT}秒）", elapsed_ms
        except requests.exceptions.ConnectionError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            detail = str(exc).lower()
            if "getaddrinfo" in detail or "name resolution" in detail or "enotfound" in detail:
                return False, "失败 · 找不到服务器（检查 API 地址、网络或 DNS）", elapsed_ms
            return False, "失败 · 无法连接服务器（检查网络和 API 地址）", elapsed_ms
        except requests.exceptions.RequestException:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return False, "失败 · 请求异常（未泄露 API Key）", elapsed_ms
