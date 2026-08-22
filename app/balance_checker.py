"""Honest provider balance checks with explicit data-source semantics."""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional
from urllib.parse import quote, urlparse

import requests


PORTAL_URLS = {
    "longcat": "https://longcat.chat/platform/",
    "deepseek": "https://platform.deepseek.com/balance",
    "anthropic": "https://console.anthropic.com/",
    "openai": "https://platform.openai.com/usage",
    "google": "https://aistudio.google.com/usage",
}

UNSUPPORTED_REASONS = {
    "longcat": "LongCat 公共文档未提供账户余额 API；请在平台 Usage 页面查看真实剩余",
    "anthropic": "Anthropic 未向普通 API Key 提供账户余额查询接口；请在 Console 查看",
    "openai": "普通 API Key 不应调用旧版账单端点；请在 Usage 控制台查看",
    "google": "Gemini 余额与用量需在 Google AI Studio Billing / Usage 中查看",
    "gcli2api": "gcli2api 使用 Google OAuth 凭据；请在本地面板查看凭据配额",
    "custom": "该供应商没有已验证的公开余额接口",
}


class BalanceInfo:
    """One provider balance result with a truthful source/status label."""

    def __init__(self, provider: str, balance: float = 0, total_grant: float = 0,
                 used: float = 0, currency: str = "USD", percent_remaining: float = -1,
                 last_updated: int = 0, status: str = "unknown", error: str = "",
                 source: str = "", portal_url: str = "", supports_balance: bool = False):
        self.provider = provider
        self.balance = balance
        self.total_grant = total_grant
        self.used = used
        self.currency = currency
        self.percent_remaining = percent_remaining
        self.last_updated = last_updated
        self.status = status
        self.error = error
        self.source = source
        self.portal_url = portal_url
        self.supports_balance = supports_balance

    def to_dict(self) -> Dict:
        return {
            "provider": self.provider, "balance": self.balance,
            "total_grant": self.total_grant, "used": self.used,
            "currency": self.currency, "percent_remaining": self.percent_remaining,
            "last_updated": self.last_updated, "status": self.status,
            "error": self.error, "source": self.source,
            "portal_url": self.portal_url, "supports_balance": self.supports_balance,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "BalanceInfo":
        allowed = cls.__init__.__code__.co_varnames
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def format_summary(self) -> str:
        if self.status == "error":
            return f"{self.provider}: 检测失败 - {self.error}"
        if self.status in {"unsupported", "unknown"}:
            return f"{self.provider}: 不支持自动查询 - {self.error}"
        if self.percent_remaining >= 0:
            return f"{self.provider}: 剩余 {self.percent_remaining:.0f}% ({self.currency} {self.balance:.2f})"
        return f"{self.provider}: 官方余额 {self.currency} {self.balance:.2f}"


class BalanceChecker:
    """Query only documented, allowlisted account-balance endpoints."""

    def __init__(self, logger=None):
        self.logger = logger
        self._cache: Dict[str, BalanceInfo] = {}
        self._cache_lock = threading.Lock()
        self._refresh_timer: Optional[threading.Timer] = None
        self._auto_refresh = False
        self._refresh_interval = 300
        self._callbacks: List[Callable] = []

    @staticmethod
    def infer_provider_type(provider: Dict) -> str:
        explicit = str(provider.get("provider_kind") or provider.get("type") or "").lower()
        name = str(provider.get("name") or "").lower()
        host = (urlparse(str(provider.get("base_url") or "")).hostname or "").lower()
        combined = " ".join((explicit, name, host))
        if "gcli2api" in combined:
            return "gcli2api"
        if "longcat" in combined or host.endswith("longcat.chat"):
            return "longcat"
        if "deepseek" in combined or host.endswith("deepseek.com"):
            return "deepseek"
        if "anthropic" in combined or host.endswith("anthropic.com"):
            return "anthropic"
        if "google" in combined or "gemini" in combined or host.endswith("googleapis.com"):
            return "google"
        if "openai" in combined or host.endswith("openai.com"):
            return "openai"
        return explicit if explicit in UNSUPPORTED_REASONS else "custom"

    @staticmethod
    def _unsupported(provider_type: str, provider_name: str, base_url: str = "") -> BalanceInfo:
        portal = base_url if provider_type == "gcli2api" else PORTAL_URLS.get(provider_type, "")
        return BalanceInfo(
            provider=provider_name or provider_type, status="unsupported",
            error=UNSUPPORTED_REASONS.get(provider_type, UNSUPPORTED_REASONS["custom"]),
            source="供应商控制台", portal_url=portal, supports_balance=False,
            last_updated=int(time.time()))

    def check_balance(self, provider_type: str, api_key: str,
                      base_url: str = "", provider_name: str = "") -> BalanceInfo:
        normalized = (provider_type or "custom").strip().lower()
        name = provider_name or normalized
        if normalized == "deepseek":
            result = self._check_deepseek_balance(api_key, provider_name=name)
        elif normalized == "gcli2api":
            result = self._check_gcli2api_quota(api_key, base_url, provider_name=name)
        else:
            result = self._unsupported(normalized, name, base_url)
        with self._cache_lock:
            self._cache[name] = result
        return result

    def _check_deepseek_balance(self, api_key: str, base_url: str = "",
                                provider_name: str = "DeepSeek") -> BalanceInfo:
        common = {
            "provider": provider_name, "source": "DeepSeek 官方余额 API",
            "portal_url": PORTAL_URLS["deepseek"], "supports_balance": True,
            "last_updated": int(time.time()),
        }
        if not api_key:
            return BalanceInfo(status="error", error="API Key 未设置", **common)
        try:
            response = requests.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=15, allow_redirects=False)
        except requests.exceptions.Timeout:
            return BalanceInfo(status="error", error="官方余额接口请求超时", **common)
        except requests.exceptions.RequestException:
            return BalanceInfo(status="error", error="无法连接官方余额接口", **common)

        if response.status_code == 401:
            error = "API Key 无效"
        elif response.status_code in {402, 403}:
            error = "余额不足或无余额查询权限"
        elif 300 <= response.status_code < 400:
            error = "官方接口返回重定向，已停止以保护密钥"
        elif response.status_code != 200:
            error = f"官方余额接口返回 HTTP {response.status_code}"
        else:
            try:
                payload = response.json()
                balances = payload.get("balance_infos", []) if isinstance(payload, dict) else []
                item = balances[0] if balances and isinstance(balances[0], dict) else {}
                amount = float(item.get("total_balance", 0))
                currency = str(item.get("currency") or "CNY")
            except (ValueError, TypeError):
                error = "官方余额接口返回了无效数据"
            else:
                return BalanceInfo(
                    balance=amount, currency=currency, percent_remaining=-1,
                    status="official", **common)
        return BalanceInfo(status="error", error=error, **common)

    def _check_gcli2api_quota(self, api_key: str, base_url: str,
                              provider_name: str = "Gemini Antigravity") -> BalanceInfo:
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower()
        root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        common = {
            "provider": provider_name,
            "source": "gcli2api 配额接口（Google 返回）",
            "portal_url": root,
            "supports_balance": True,
            "last_updated": int(time.time()),
        }
        if not api_key:
            return BalanceInfo(status="error", error="本地 API 密码未设置", **common)
        if not root or (parsed.scheme == "http" and host not in {"127.0.0.1", "localhost", "::1"}):
            return BalanceInfo(status="error", error="gcli2api 地址不安全或无效", **common)
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            status_response = requests.get(
                f"{root}/creds/status", headers=headers,
                params={
                    "offset": 0, "limit": 50, "status_filter": "enabled",
                    "mode": "antigravity",
                },
                timeout=15, allow_redirects=False,
            )
            if status_response.status_code in {401, 403}:
                return BalanceInfo(status="error", error="面板密码与本地 API 密码不一致", **common)
            if status_response.status_code != 200:
                return BalanceInfo(
                    status="error", error=f"凭证接口返回 HTTP {status_response.status_code}", **common)
            payload = status_response.json()
            items = payload.get("items", []) if isinstance(payload, dict) else []
            filenames = [
                str(item.get("filename") or "") for item in items
                if isinstance(item, dict) and not item.get("disabled")
            ]
            all_remaining = []
            model_count = 0
            for filename in filenames[:10]:
                if not filename.endswith(".json"):
                    continue
                response = requests.get(
                    f"{root}/creds/quota/{quote(filename, safe='')}",
                    headers=headers, params={"mode": "antigravity"},
                    timeout=30, allow_redirects=False,
                )
                if response.status_code != 200:
                    continue
                quota_payload = response.json()
                models = quota_payload.get("models", {}) if isinstance(quota_payload, dict) else {}
                if not isinstance(models, dict):
                    continue
                model_count += len(models)
                for value in models.values():
                    if not isinstance(value, dict):
                        continue
                    try:
                        remaining = float(value.get("remaining"))
                    except (TypeError, ValueError):
                        continue
                    all_remaining.append(max(0.0, min(1.0, remaining)))
        except requests.exceptions.Timeout:
            return BalanceInfo(status="error", error="gcli2api 配额查询超时", **common)
        except (requests.exceptions.RequestException, ValueError, TypeError):
            return BalanceInfo(status="error", error="无法读取 gcli2api 配额", **common)
        if not all_remaining:
            return BalanceInfo(status="error", error="没有可用的 Antigravity 配额数据", **common)
        minimum = min(all_remaining) * 100
        maximum = max(all_remaining) * 100
        return BalanceInfo(
            status="quota", percent_remaining=minimum,
            error=f"{model_count} 个模型 · 最低 {minimum:.0f}% · 最高 {maximum:.0f}%",
            **common,
        )

    def _check_openai_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        return self._unsupported("openai", "OpenAI", base_url)

    def _check_anthropic_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        return self._unsupported("anthropic", "Anthropic", base_url)

    def _check_google_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        return self._unsupported("google", "Google Gemini", base_url)

    def _check_generic_balance(self, provider_type: str, api_key: str,
                               base_url: str) -> BalanceInfo:
        result = self._unsupported("custom", provider_type, base_url)
        if not base_url:
            result.status = "unknown"
            result.error = "无 API 地址，且没有已验证的公开余额接口"
        return result

    def check_all(self, providers: List[Dict]) -> Dict[str, BalanceInfo]:
        results = {}
        for provider in providers:
            name = str(provider.get("name") or "unknown")
            provider_type = self.infer_provider_type(provider)
            results[name] = self.check_balance(
                provider_type, str(provider.get("api_key") or ""),
                str(provider.get("base_url") or ""), provider_name=name)
        for callback in self._callbacks:
            try:
                callback(results)
            except Exception:
                pass
        return results

    def get_cached(self, provider: str) -> Optional[BalanceInfo]:
        with self._cache_lock:
            return self._cache.get(provider)

    def get_all_cached(self) -> Dict[str, BalanceInfo]:
        with self._cache_lock:
            return dict(self._cache)

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()

    def start_auto_refresh(self, interval: int = 300, providers: List[Dict] = None,
                           callback: Callable = None):
        self._auto_refresh = True
        self._refresh_interval = interval

        def refresh():
            if not self._auto_refresh:
                return
            if providers:
                self.check_all(providers)
            if callback:
                try:
                    callback(self.get_all_cached())
                except Exception:
                    pass
            if self._auto_refresh:
                self._refresh_timer = threading.Timer(self._refresh_interval, refresh)
                self._refresh_timer.daemon = True
                self._refresh_timer.start()

        self._refresh_timer = threading.Timer(self._refresh_interval, refresh)
        self._refresh_timer.daemon = True
        self._refresh_timer.start()

    def stop_auto_refresh(self):
        self._auto_refresh = False
        if self._refresh_timer:
            self._refresh_timer.cancel()
            self._refresh_timer = None

    def on_refresh(self, callback: Callable):
        self._callbacks.append(callback)
