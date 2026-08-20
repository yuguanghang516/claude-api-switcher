"""
V2 多 Key 自动轮询模块
一个供应商支持多个 Key，例如：
Claude:
  - Key1
  - Key2
  - Key3

规则：
- 正常：优先 Key1
- Key1 限流：自动切 Key2
- Key 全部异常：切换备用模型
"""
import time
import threading
from typing import List, Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field


class KeyStatus(Enum):
    """Key 状态"""
    ACTIVE = "active"       # 可用
    RATE_LIMITED = "rate_limited"  # 限流
    EXHAUSTED = "exhausted"  # 额度用尽
    ERROR = "error"         # 错误
    DISABLED = "disabled"   # 禁用


@dataclass
class KeyInfo:
    """Key 信息"""
    key: str
    index: int
    status: KeyStatus = KeyStatus.ACTIVE
    last_used: int = 0
    use_count: int = 0
    error_count: int = 0
    last_error: str = ""
    rate_limit_reset: int = 0  # 限流重置时间戳
    consecutive_errors: int = 0

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "status": self.status.value,
            "last_used": self.last_used,
            "use_count": self.use_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "rate_limit_reset": self.rate_limit_reset,
            "consecutive_errors": self.consecutive_errors,
        }


class KeyRotationStrategy:
    """Key 轮询策略"""

    @staticmethod
    def round_robin(keys: List[KeyInfo]) -> Optional[KeyInfo]:
        """轮询策略：按顺序轮流使用"""
        available = [k for k in keys if k.status == KeyStatus.ACTIVE]
        if not available:
            return None
        # 选择使用次数最少的
        return min(available, key=lambda k: k.use_count)

    @staticmethod
    def priority(keys: List[KeyInfo]) -> Optional[KeyInfo]:
        """优先级策略：按索引顺序，优先前面的 Key"""
        available = [k for k in keys if k.status == KeyStatus.ACTIVE]
        if not available:
            return None
        return min(available, key=lambda k: k.index)

    @staticmethod
    def least_used(keys: List[KeyInfo]) -> Optional[KeyInfo]:
        """最少使用策略：选择使用次数最少的"""
        available = [k for k in keys if k.status == KeyStatus.ACTIVE]
        if not available:
            return None
        return min(available, key=lambda k: k.use_count)

    @staticmethod
    def least_recently_used(keys: List[KeyInfo]) -> Optional[KeyInfo]:
        """最近最少使用"""
        available = [k for k in keys if k.status == KeyStatus.ACTIVE]
        if not available:
            return None
        return min(available, key=lambda k: k.last_used)


class MultiKeyRotator:
    """多 Key 自动轮询器"""

    def __init__(self, strategy: str = "round_robin", max_consecutive_errors: int = 3,
                 cooldown_seconds: int = 60, logger=None):
        """
        :param strategy: 轮询策略 (round_robin | priority | least_used | least_recently_used)
        :param max_consecutive_errors: 连续错误次数上限
        :param cooldown_seconds: 错误冷却时间（秒）
        """
        self._keys: Dict[str, List[KeyInfo]] = {}  # {provider_id: [KeyInfo, ...]}
        self._current_index: Dict[str, int] = {}  # {provider_id: current_index}
        self._strategy = strategy
        self._max_consecutive_errors = max_consecutive_errors
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.RLock()
        self.logger = logger

        self._strategies = {
            "round_robin": KeyRotationStrategy.round_robin,
            "priority": KeyRotationStrategy.priority,
            "least_used": KeyRotationStrategy.least_used,
            "least_recently_used": KeyRotationStrategy.least_recently_used,
        }

    def set_keys(self, provider_id: str, keys: List[str]):
        """设置供应商的 Key 列表"""
        with self._lock:
            key_infos = []
            for i, key in enumerate(keys):
                key = key.strip()
                if key:
                    key_infos.append(KeyInfo(key=key, index=i))
            self._keys[provider_id] = key_infos
            self._current_index[provider_id] = 0

    def add_key(self, provider_id: str, api_key: str):
        """添加一个 Key"""
        with self._lock:
            if provider_id not in self._keys:
                self._keys[provider_id] = []
            api_key = api_key.strip()
            if api_key and not any(k.key == api_key for k in self._keys[provider_id]):
                self._keys[provider_id].append(
                    KeyInfo(key=api_key, index=len(self._keys[provider_id]))
                )

    def remove_key(self, provider_id: str, index: int) -> bool:
        """删除指定索引的 Key"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            if 0 <= index < len(keys):
                keys.pop(index)
                # 重新编号
                for i, k in enumerate(keys):
                    k.index = i
                return True
            return False

    def get_current_key(self, provider_id: str) -> Optional[str]:
        """获取当前应使用的 Key"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            if not keys:
                return None

            strategy_func = self._strategies.get(self._strategy, KeyRotationStrategy.round_robin)
            selected = strategy_func(keys)

            if selected:
                return selected.key
            return None

    def get_next_key(self, provider_id: str) -> Optional[str]:
        """获取下一个可用的 Key（当前 Key 失败时调用）"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            if not keys:
                return None

            # 找到当前 Key 并标记为错误
            current_idx = self._current_index.get(provider_id, 0)
            if 0 <= current_idx < len(keys):
                keys[current_idx].status = KeyStatus.ERROR
                keys[current_idx].consecutive_errors += 1

            # 选择下一个可用的 Key
            available = [k for k in keys if k.status == KeyStatus.ACTIVE]
            if available:
                selected = min(available, key=lambda k: k.index)
                self._current_index[provider_id] = selected.index
                return selected.key

            # 所有 Key 都不可用，尝试重置冷却期过的 Key
            now = int(time.time())
            for k in keys:
                if k.status == KeyStatus.RATE_LIMITED and now >= k.rate_limit_reset:
                    k.status = KeyStatus.ACTIVE
                    k.consecutive_errors = 0
                elif k.status == KeyStatus.ERROR and k.consecutive_errors < self._max_consecutive_errors:
                    k.status = KeyStatus.ACTIVE

            available = [k for k in keys if k.status == KeyStatus.ACTIVE]
            if available:
                selected = min(available, key=lambda k: k.index)
                self._current_index[provider_id] = selected.index
                return selected.key

            return None

    def report_success(self, provider_id: str, api_key: str):
        """报告 Key 使用成功"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            for k in keys:
                if k.key == api_key:
                    k.last_used = int(time.time())
                    k.use_count += 1
                    k.consecutive_errors = 0
                    if k.status == KeyStatus.ERROR:
                        k.status = KeyStatus.ACTIVE
                    break

    def report_error(self, provider_id: str, api_key: str, error: str,
                     is_rate_limit: bool = False):
        """
        报告 Key 使用错误
        :param is_rate_limit: 是否为限流错误
        """
        with self._lock:
            keys = self._keys.get(provider_id, [])
            for k in keys:
                if k.key == api_key:
                    k.error_count += 1
                    k.consecutive_errors += 1
                    k.last_error = error[:200]

                    if is_rate_limit:
                        k.status = KeyStatus.RATE_LIMITED
                        # 默认 60 秒后重试
                        k.rate_limit_reset = int(time.time()) + 60
                    elif k.consecutive_errors >= self._max_consecutive_errors:
                        k.status = KeyStatus.EXHAUSTED
                    else:
                        k.status = KeyStatus.ERROR
                    break

    def report_rate_limit(self, provider_id: str, api_key: str,
                          reset_seconds: int = 60):
        """报告 Key 被限流"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            for k in keys:
                if k.key == api_key:
                    k.status = KeyStatus.RATE_LIMITED
                    k.rate_limit_reset = int(time.time()) + reset_seconds
                    k.last_error = f"Rate limited, reset in {reset_seconds}s"
                    break

    def get_key_status(self, provider_id: str) -> List[Dict]:
        """获取所有 Key 的状态"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            return [k.to_dict() for k in keys]

    def get_active_key_count(self, provider_id: str) -> int:
        """获取可用 Key 数量"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            return sum(1 for k in keys if k.status == KeyStatus.ACTIVE)

    def get_total_key_count(self, provider_id: str) -> int:
        """获取总 Key 数量"""
        with self._lock:
            return len(self._keys.get(provider_id, []))

    def has_available_key(self, provider_id: str) -> bool:
        """是否有可用的 Key"""
        return self.get_active_key_count(provider_id) > 0

    def reset_all_keys(self, provider_id: str):
        """重置所有 Key 状态"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            for k in keys:
                k.status = KeyStatus.ACTIVE
                k.consecutive_errors = 0
                k.rate_limit_reset = 0

    def get_all_providers(self) -> List[str]:
        """获取所有已配置的供应商 ID"""
        with self._lock:
            return list(self._keys.keys())

    def set_strategy(self, strategy: str):
        """设置轮询策略"""
        if strategy in self._strategies:
            self._strategy = strategy

    def get_rotation_summary(self, provider_id: str) -> Dict:
        """获取轮询摘要"""
        with self._lock:
            keys = self._keys.get(provider_id, [])
            if not keys:
                return {"total": 0, "active": 0, "rate_limited": 0, "error": 0, "exhausted": 0}

            summary = {
                "total": len(keys),
                "active": sum(1 for k in keys if k.status == KeyStatus.ACTIVE),
                "rate_limited": sum(1 for k in keys if k.status == KeyStatus.RATE_LIMITED),
                "error": sum(1 for k in keys if k.status == KeyStatus.ERROR),
                "exhausted": sum(1 for k in keys if k.status == KeyStatus.EXHAUSTED),
                "disabled": sum(1 for k in keys if k.status == KeyStatus.DISABLED),
                "strategy": self._strategy,
            }
            return summary
