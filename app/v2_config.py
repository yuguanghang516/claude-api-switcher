"""
V2 智能 AI Gateway 配置管理模块
负责读取和保存 V2 相关配置：
- 多 Key 配置
- 路由规则
- 预算控制
- 通知设置
- 热切换配置

写入策略：原子写入 + 回滚保护
"""
import os
import json
import tempfile
import copy
import time
import threading
from typing import List, Dict, Any, Optional, Callable


# 默认 V2 配置
DEFAULT_V2_CONFIG = {
    # ===== 多 Key 配置 =====
    "multi_keys": {},  # {provider_id: [key1, key2, ...]}
    "key_rotation_enabled": True,
    "key_rotation_strategy": "round_robin",  # round_robin | least_used | priority

    # ===== 路由规则 =====
    "routing_rules": {
        "code": {
            "description": "代码任务",
            "preferred_models": ["claude-sonnet-4-20250514", "deepseek-chat"],
            "fallback_models": ["gpt-4o", "moonshot-v1-32k"],
            "enabled": True,
        },
        "chat": {
            "description": "普通聊天",
            "preferred_models": ["gpt-4o", "gemini-1.5-flash"],
            "fallback_models": ["claude-3-5-haiku-20241022", "deepseek-chat"],
            "enabled": True,
        },
        "cheap": {
            "description": "低成本",
            "preferred_models": ["deepseek-chat", "moonshot-v1-8k"],
            "fallback_models": ["gpt-4o-mini", "LongCat-Flash-Chat"],
            "enabled": True,
        },
        "complex": {
            "description": "复杂任务",
            "preferred_models": ["claude-opus-4-20250514", "gpt-4o"],
            "fallback_models": ["claude-sonnet-4-20250514", "deepseek-reasoner"],
            "enabled": True,
        },
    },
    "routing_enabled": True,
    "default_task_type": "chat",

    # ===== 预算控制 =====
    "budget": {
        "daily_limit_usd": 5.0,
        "monthly_limit_usd": 100.0,
        "warning_threshold": 0.8,  # 80% 提醒
        "auto_switch_cheap": True,  # 100% 自动切换低成本
        "currency": "USD",  # USD | CNY
    },

    # ===== 通知设置 =====
    "notifications": {
        "enabled": True,
        "desktop_enabled": True,
        "webhook_enabled": False,
        "webhook_url": "",
        "alert_on_low_balance": True,
        "low_balance_threshold": 10,  # 剩余少于 $10 提醒
        "alert_on_api_error": True,
        "alert_on_budget_exceeded": True,
    },

    # ===== 余额检测 =====
    "balance_check": {
        "enabled": True,
        "auto_refresh_interval": 300,  # 秒，默认 5 分钟
        "last_check": 0,
    },

    # ===== 故障转移 =====
    "failover": {
        "enabled": True,
        "max_retries": 3,
        "retry_delay_ms": 1000,
        "timeout_seconds": 30,
        "circuit_breaker_threshold": 5,  # 连续失败次数触发熔断
        "circuit_breaker_reset_seconds": 60,  # 熔断重置时间
    },

    # ===== 热切换 =====
    "hot_reload": {
        "enabled": True,
        "watch_interval": 2,  # 秒
    },
}


class V2ConfigManager:
    """V2 配置管理器 - 支持热切换"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.config_file = os.path.join(data_dir, "v2_config.json")
        self.config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._change_callbacks: List[Callable] = []
        self._ensure_data_dir()
        self._load_config()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                # 合并新增默认字段
                self._merge_defaults()
            except (json.JSONDecodeError, IOError):
                self._create_default_config()
        else:
            self._create_default_config()

    def _merge_defaults(self):
        """合并新增的默认配置字段（升级时自动补齐）"""
        changed = False
        for key, value in DEFAULT_V2_CONFIG.items():
            if key not in self.config:
                self.config[key] = copy.deepcopy(value)
                changed = True
            elif isinstance(value, dict) and isinstance(self.config[key], dict):
                for sub_key, sub_value in value.items():
                    if sub_key not in self.config[key]:
                        self.config[key][sub_key] = copy.deepcopy(sub_value)
                        changed = True
        if changed:
            self._save_config()

    def _create_default_config(self):
        """创建默认配置"""
        self.config = copy.deepcopy(DEFAULT_V2_CONFIG)
        self._save_config()

    def _save_config(self):
        """原子写入配置"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=self.data_dir, suffix=".tmp", prefix="v2_config_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.config_file)
            except Exception:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                raise
        except OSError as e:
            raise IOError(f"保存 V2 配置失败: {e}") from e

    def _save_with_rollback(self, previous: Dict[str, Any]) -> bool:
        """带回滚的保存"""
        try:
            self._save_config()
            return True
        except IOError:
            self.config = previous
            return False

    def save(self) -> bool:
        """手动保存配置"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            return self._save_with_rollback(previous)

    def reload(self):
        """重新加载配置（热切换用）"""
        with self._lock:
            old_config = copy.deepcopy(self.config)
            try:
                if os.path.exists(self.config_file):
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        self.config = json.load(f)
                    self._merge_defaults()
                    # 通知监听器
                    self._notify_change(old_config, self.config)
            except Exception:
                self.config = old_config

    def on_change(self, callback: Callable):
        """注册配置变更回调"""
        self._change_callbacks.append(callback)

    def _notify_change(self, old: Dict, new: Dict):
        """通知配置变更"""
        for cb in self._change_callbacks:
            try:
                cb(old, new)
            except Exception:
                pass

    # ===== 多 Key 配置 =====

    def get_multi_keys(self, provider_id: str) -> List[str]:
        """获取供应商的多 Key 列表"""
        with self._lock:
            return self.config.get("multi_keys", {}).get(provider_id, [])

    def set_multi_keys(self, provider_id: str, keys: List[str]) -> bool:
        """设置供应商的多 Key 列表"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            if "multi_keys" not in self.config:
                self.config["multi_keys"] = {}
            self.config["multi_keys"][provider_id] = [k for k in keys if k.strip()]
            return self._save_with_rollback(previous)

    def add_key(self, provider_id: str, api_key: str) -> bool:
        """添加一个 Key"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            if "multi_keys" not in self.config:
                self.config["multi_keys"] = {}
            if provider_id not in self.config["multi_keys"]:
                self.config["multi_keys"][provider_id] = []
            key = api_key.strip()
            if key and key not in self.config["multi_keys"][provider_id]:
                self.config["multi_keys"][provider_id].append(key)
            return self._save_with_rollback(previous)

    def remove_key(self, provider_id: str, index: int) -> bool:
        """删除指定索引的 Key"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            keys = self.config.get("multi_keys", {}).get(provider_id, [])
            if 0 <= index < len(keys):
                keys.pop(index)
                return self._save_with_rollback(previous)
            return False

    def is_key_rotation_enabled(self) -> bool:
        """是否启用 Key 轮询"""
        with self._lock:
            return self.config.get("key_rotation_enabled", True)

    def get_rotation_strategy(self) -> str:
        """获取轮询策略"""
        with self._lock:
            return self.config.get("key_rotation_strategy", "round_robin")

    # ===== 路由规则 =====

    def get_routing_rules(self) -> Dict[str, Any]:
        """获取所有路由规则"""
        with self._lock:
            return copy.deepcopy(self.config.get("routing_rules", {}))

    def get_routing_rule(self, task_type: str) -> Optional[Dict[str, Any]]:
        """获取指定任务类型的路由规则"""
        with self._lock:
            return copy.deepcopy(self.config.get("routing_rules", {}).get(task_type))

    def set_routing_rule(self, task_type: str, rule: Dict[str, Any]) -> bool:
        """设置路由规则"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            if "routing_rules" not in self.config:
                self.config["routing_rules"] = {}
            self.config["routing_rules"][task_type] = copy.deepcopy(rule)
            return self._save_with_rollback(previous)

    def is_routing_enabled(self) -> bool:
        """是否启用智能路由"""
        with self._lock:
            return self.config.get("routing_enabled", True)

    def set_routing_enabled(self, enabled: bool) -> bool:
        """设置路由开关"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            self.config["routing_enabled"] = enabled
            return self._save_with_rollback(previous)

    def get_default_task_type(self) -> str:
        """获取默认任务类型"""
        with self._lock:
            return self.config.get("default_task_type", "chat")

    # ===== 预算控制 =====

    def get_budget(self) -> Dict[str, Any]:
        """获取预算配置"""
        with self._lock:
            return copy.deepcopy(self.config.get("budget", DEFAULT_V2_CONFIG["budget"]))

    def set_budget(self, budget: Dict[str, Any]) -> bool:
        """设置预算配置"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            self.config["budget"] = copy.deepcopy(budget)
            return self._save_with_rollback(previous)

    def get_daily_limit(self) -> float:
        """获取每日预算"""
        with self._lock:
            return self.config.get("budget", {}).get("daily_limit_usd", 5.0)

    def get_monthly_limit(self) -> float:
        """获取每月预算"""
        with self._lock:
            return self.config.get("budget", {}).get("monthly_limit_usd", 100.0)

    # ===== 通知设置 =====

    def get_notifications(self) -> Dict[str, Any]:
        """获取通知配置"""
        with self._lock:
            return copy.deepcopy(self.config.get("notifications", DEFAULT_V2_CONFIG["notifications"]))

    def set_notifications(self, notifications: Dict[str, Any]) -> bool:
        """设置通知配置"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            self.config["notifications"] = copy.deepcopy(notifications)
            return self._save_with_rollback(previous)

    # ===== 余额检测 =====

    def get_balance_check(self) -> Dict[str, Any]:
        """获取余额检测配置"""
        with self._lock:
            return copy.deepcopy(self.config.get("balance_check", DEFAULT_V2_CONFIG["balance_check"]))

    def set_last_balance_check(self, timestamp: int):
        """设置最后检测时间"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            if "balance_check" not in self.config:
                self.config["balance_check"] = {}
            self.config["balance_check"]["last_check"] = timestamp
            self._save_with_rollback(previous)

    # ===== 故障转移 =====

    def get_failover(self) -> Dict[str, Any]:
        """获取故障转移配置"""
        with self._lock:
            return copy.deepcopy(self.config.get("failover", DEFAULT_V2_CONFIG["failover"]))

    def set_failover(self, failover: Dict[str, Any]) -> bool:
        """设置故障转移配置"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            self.config["failover"] = copy.deepcopy(failover)
            return self._save_with_rollback(previous)

    # ===== 热切换 =====

    def is_hot_reload_enabled(self) -> bool:
        """是否启用热切换"""
        with self._lock:
            return self.config.get("hot_reload", {}).get("enabled", True)

    def get_watch_interval(self) -> int:
        """获取监控间隔"""
        with self._lock:
            return self.config.get("hot_reload", {}).get("watch_interval", 2)

    # ===== 导入导出 =====

    def export_config(self) -> Dict[str, Any]:
        """导出完整配置"""
        with self._lock:
            return copy.deepcopy(self.config)

    def import_config(self, data: Dict[str, Any]) -> bool:
        """导入配置"""
        with self._lock:
            previous = copy.deepcopy(self.config)
            self.config = copy.deepcopy(data)
            return self._save_with_rollback(previous)
