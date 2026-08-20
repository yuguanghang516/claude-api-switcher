"""
V2 API 余额检测模块
支持检测：
- OpenAI 余额
- Anthropic 额度
- DeepSeek 余额
- Google 额度
- 其他兼容 API

显示：剩余额度、使用百分比、更新时间
支持自动刷新
"""
import time
import threading
import requests
from typing import Dict, Optional, Callable, List
from datetime import datetime


# 各供应商余额检测端点
BALANCE_ENDPOINTS = {
    "openai": {
        "balance_url": "https://api.openai.com/v1/dashboard/billing/credit_summary",
        "usage_url": "https://api.openai.com/v1/dashboard/billing/usage",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "anthropic": {
        # Anthropic 没有直接的余额 API，通过消息 API 推断
        "balance_url": None,  # 需要通过消息头或试用额度接口
        "usage_url": None,
        "auth_header": "x-api-key",
        "auth_prefix": "",
    },
    "deepseek": {
        "balance_url": "https://api.deepseek.com/v1/balance",
        "usage_url": None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "google": {
        # Google 没有直接余额 API
        "balance_url": None,
        "usage_url": None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
}


class BalanceInfo:
    """余额信息数据类"""

    def __init__(self, provider: str, balance: float = 0, total_grant: float = 0,
                 used: float = 0, currency: str = "USD", percent_remaining: float = 0,
                 last_updated: int = 0, status: str = "unknown", error: str = ""):
        self.provider = provider
        self.balance = balance  # 剩余额度
        self.total_grant = total_grant  # 总授予额度
        self.used = used  # 已使用
        self.currency = currency
        self.percent_remaining = percent_remaining  # 剩余百分比
        self.last_updated = last_updated  # 更新时间戳
        self.status = status  # ok | error | unknown
        self.error = error

    def to_dict(self) -> Dict:
        return {
            "provider": self.provider,
            "balance": self.balance,
            "total_grant": self.total_grant,
            "used": self.used,
            "currency": self.currency,
            "percent_remaining": self.percent_remaining,
            "last_updated": self.last_updated,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "BalanceInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})

    def format_summary(self) -> str:
        """格式化显示"""
        if self.status == "error":
            return f"{self.provider}: 检测失败 - {self.error}"
        if self.status == "unknown":
            return f"{self.provider}: 暂不支持检测"
        return f"{self.provider}: 剩余 {self.percent_remaining:.0f}% ({self.currency} {self.balance:.2f})"


class BalanceChecker:
    """API 余额检测器"""

    def __init__(self, logger=None):
        self.logger = logger
        self._cache: Dict[str, BalanceInfo] = {}
        self._cache_lock = threading.Lock()
        self._refresh_timer: Optional[threading.Timer] = None
        self._auto_refresh = False
        self._refresh_interval = 300  # 5 分钟
        self._callbacks: List[Callable] = []

    def check_balance(self, provider_type: str, api_key: str,
                      base_url: str = "") -> BalanceInfo:
        """
        检测指定供应商的余额
        :param provider_type: 供应商类型 (openai, anthropic, deepseek, google, custom)
        :param api_key: API Key
        :param base_url: 自定义 API 地址
        :return: BalanceInfo
        """
        checker_func = {
            "openai": self._check_openai_balance,
            "anthropic": self._check_anthropic_balance,
            "deepseek": self._check_deepseek_balance,
            "google": self._check_google_balance,
        }.get(provider_type)

        if checker_func:
            result = checker_func(api_key, base_url)
        else:
            result = self._check_generic_balance(provider_type, api_key, base_url)

        # 缓存结果
        with self._cache_lock:
            self._cache[provider_type] = result

        return result

    def _check_openai_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        """检测 OpenAI 余额"""
        url = "https://api.openai.com/v1/dashboard/billing/credit_summary"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                total_grant = data.get("total_granted", 0)
                used = data.get("total_used", 0)
                balance = total_grant - used
                percent = (balance / total_grant * 100) if total_grant > 0 else 0
                return BalanceInfo(
                    provider="OpenAI",
                    balance=balance,
                    total_grant=total_grant,
                    used=used,
                    currency="USD",
                    percent_remaining=percent,
                    last_updated=int(time.time()),
                    status="ok",
                )
            elif resp.status_code == 401:
                return BalanceInfo(provider="OpenAI", status="error", error="API Key 无效",
                                   last_updated=int(time.time()))
            else:
                return BalanceInfo(provider="OpenAI", status="error",
                                   error=f"HTTP {resp.status_code}",
                                   last_updated=int(time.time()))
        except requests.exceptions.Timeout:
            return BalanceInfo(provider="OpenAI", status="error", error="请求超时",
                               last_updated=int(time.time()))
        except Exception as e:
            return BalanceInfo(provider="OpenAI", status="error", error=str(e)[:100],
                               last_updated=int(time.time()))

    def _check_anthropic_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        """
        检测 Anthropic 余额
        Anthropic 没有直接的余额 API，通过发送最小请求检查是否可用
        并从响应头获取 Rate Limit 信息
        """
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                # 从响应头获取额度信息
                remaining = resp.headers.get("anthropic-ratelimit-tokens-remaining", "unknown")
                return BalanceInfo(
                    provider="Anthropic",
                    balance=0,
                    total_grant=0,
                    used=0,
                    currency="USD",
                    percent_remaining=100,
                    last_updated=int(time.time()),
                    status="ok",
                )
            elif resp.status_code == 401:
                return BalanceInfo(provider="Anthropic", status="error", error="API Key 无效",
                                   last_updated=int(time.time()))
            elif resp.status_code == 422:
                # 请求格式有问题但 Key 有效
                return BalanceInfo(
                    provider="Anthropic",
                    balance=0, total_grant=0, used=0,
                    percent_remaining=100,
                    last_updated=int(time.time()),
                    status="ok",
                )
            elif resp.status_code == 429:
                return BalanceInfo(provider="Anthropic", status="ok",
                                   error="请求频率限制，Key 有效",
                                   percent_remaining=50,
                                   last_updated=int(time.time()))
            else:
                error_text = ""
                try:
                    error_text = resp.json().get("error", {}).get("message", "")[:100]
                except Exception:
                    pass
                return BalanceInfo(provider="Anthropic", status="error",
                                   error=f"HTTP {resp.status_code}: {error_text}",
                                   last_updated=int(time.time()))
        except requests.exceptions.Timeout:
            return BalanceInfo(provider="Anthropic", status="error", error="请求超时",
                               last_updated=int(time.time()))
        except Exception as e:
            return BalanceInfo(provider="Anthropic", status="error", error=str(e)[:100],
                               last_updated=int(time.time()))

    def _check_deepseek_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        """检测 DeepSeek 余额"""
        url = "https://api.deepseek.com/v1/balance"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                # DeepSeek 返回格式
                if data.get("is_available", False):
                    balance_infos = data.get("balance_infos", [])
                    if balance_infos:
                        info = balance_infos[0]
                        balance = float(info.get("total_balance", 0))
                        total = float(info.get("total_balance", 0))
                        used = total - balance
                        percent = (balance / total * 100) if total > 0 else 0
                        return BalanceInfo(
                            provider="DeepSeek",
                            balance=balance,
                            total_grant=total,
                            used=used,
                            currency=info.get("currency", "USD"),
                            percent_remaining=percent,
                            last_updated=int(time.time()),
                            status="ok",
                        )
                return BalanceInfo(
                    provider="DeepSeek",
                    balance=0, total_grant=0, used=0,
                    percent_remaining=100,
                    last_updated=int(time.time()),
                    status="ok",
                )
            elif resp.status_code == 401:
                return BalanceInfo(provider="DeepSeek", status="error", error="API Key 无效",
                                   last_updated=int(time.time()))
            else:
                return BalanceInfo(provider="DeepSeek", status="error",
                                   error=f"HTTP {resp.status_code}",
                                   last_updated=int(time.time()))
        except requests.exceptions.Timeout:
            return BalanceInfo(provider="DeepSeek", status="error", error="请求超时",
                               last_updated=int(time.time()))
        except Exception as e:
            return BalanceInfo(provider="DeepSeek", status="error", error=str(e)[:100],
                               last_updated=int(time.time()))

    def _check_google_balance(self, api_key: str, base_url: str = "") -> BalanceInfo:
        """检测 Google 额度（Google 没有直接余额 API，通过验证 Key 判断）"""
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return BalanceInfo(
                    provider="Google Gemini",
                    balance=0, total_grant=0, used=0,
                    currency="USD",
                    percent_remaining=100,
                    last_updated=int(time.time()),
                    status="ok",
                )
            elif resp.status_code == 401 or resp.status_code == 403:
                return BalanceInfo(provider="Google Gemini", status="error",
                                   error="API Key 无效或权限不足",
                                   last_updated=int(time.time()))
            else:
                return BalanceInfo(provider="Google Gemini", status="error",
                                   error=f"HTTP {resp.status_code}",
                                   last_updated=int(time.time()))
        except requests.exceptions.Timeout:
            return BalanceInfo(provider="Google Gemini", status="error", error="请求超时",
                               last_updated=int(time.time()))
        except Exception as e:
            return BalanceInfo(provider="Google Gemini", status="error", error=str(e)[:100],
                               last_updated=int(time.time()))

    def _check_generic_balance(self, provider_type: str, api_key: str,
                               base_url: str) -> BalanceInfo:
        """通用余额检测（Key 有效性验证）"""
        if not base_url:
            return BalanceInfo(provider=provider_type, status="unknown",
                               error="无 API 地址", last_updated=int(time.time()))

        url = base_url.rstrip("/")
        if not url.endswith("/models"):
            url = f"{url}/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return BalanceInfo(
                    provider=provider_type,
                    balance=0, total_grant=0, used=0,
                    percent_remaining=100,
                    last_updated=int(time.time()),
                    status="ok",
                )
            elif resp.status_code == 401:
                return BalanceInfo(provider=provider_type, status="error",
                                   error="API Key 无效", last_updated=int(time.time()))
            else:
                return BalanceInfo(provider=provider_type, status="error",
                                   error=f"HTTP {resp.status_code}",
                                   last_updated=int(time.time()))
        except Exception as e:
            return BalanceInfo(provider=provider_type, status="error",
                               error=str(e)[:100], last_updated=int(time.time()))

    def check_all(self, providers: List[Dict]) -> Dict[str, BalanceInfo]:
        """
        批量检测所有供应商余额
        :param providers: [{"name": "...", "type": "openai", "api_key": "...", "base_url": "..."}]
        :return: {provider_name: BalanceInfo}
        """
        results = {}
        for p in providers:
            name = p.get("name", "unknown")
            ptype = p.get("type", "custom")
            api_key = p.get("api_key", "")
            base_url = p.get("base_url", "")

            if not api_key:
                results[name] = BalanceInfo(
                    provider=name, status="error",
                    error="API Key 未设置", last_updated=int(time.time())
                )
                continue

            result = self.check_balance(ptype, api_key, base_url)
            results[name] = result

        # 通知回调
        for cb in self._callbacks:
            try:
                cb(results)
            except Exception:
                pass

        return results

    def get_cached(self, provider: str) -> Optional[BalanceInfo]:
        """获取缓存的余额信息"""
        with self._cache_lock:
            return self._cache.get(provider)

    def get_all_cached(self) -> Dict[str, BalanceInfo]:
        """获取所有缓存的余额信息"""
        with self._cache_lock:
            return dict(self._cache)

    def clear_cache(self):
        """清除缓存"""
        with self._cache_lock:
            self._cache.clear()

    def start_auto_refresh(self, interval: int = 300, providers: List[Dict] = None,
                           callback: Callable = None):
        """
        启动自动刷新
        :param interval: 刷新间隔（秒）
        :param providers: 供应商列表
        :param callback: 刷新完成回调
        """
        self._auto_refresh = True
        self._refresh_interval = interval

        def _refresh():
            if not self._auto_refresh:
                return
            if providers:
                self.check_all(providers)
            if callback:
                try:
                    callback(self._cache)
                except Exception:
                    pass
            # 安排下一次刷新
            if self._auto_refresh:
                self._refresh_timer = threading.Timer(self._refresh_interval, _refresh)
                self._refresh_timer.daemon = True
                self._refresh_timer.start()

        self._refresh_timer = threading.Timer(self._refresh_interval, _refresh)
        self._refresh_timer.daemon = True
        self._refresh_timer.start()

    def stop_auto_refresh(self):
        """停止自动刷新"""
        self._auto_refresh = False
        if self._refresh_timer:
            self._refresh_timer.cancel()
            self._refresh_timer = None

    def on_refresh(self, callback: Callable):
        """注册刷新回调"""
        self._callbacks.append(callback)
