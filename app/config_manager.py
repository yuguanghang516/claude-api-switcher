"""
配置管理模块
负责读取和保存非敏感配置到 JSON 文件
API Key 不保存在此文件中，而是使用 CredentialManager

写入策略：原子写入 + 回滚保护
- 先写入临时文件，再原子替换
- 写入失败时自动回滚，不损坏现有配置
"""
import os
import json
import tempfile
import copy
import uuid
from typing import List, Dict, Any, Optional


# 默认 Provider 配置
DEFAULT_PROVIDERS: List[Dict[str, Any]] = [
    {
        "name": "LongCat",
        "base_url": "https://api.longcat.chat/anthropic",
        "model": "LongCat-2.0",
        "small_fast_model": "LongCat-2.0",
        "enabled": True,
        "priority": 1,
        "is_fallback": False,
        "auth_mode": "bearer",
        "provider_kind": "longcat",
    },
    {
        "name": "DeepSeek",
        "base_url": "",  # 用户自行填写
        "model": "",
        "small_fast_model": "",
        "enabled": False,
        "priority": 2,
        "is_fallback": False,
        "auth_mode": "bearer",
        "provider_kind": "custom",
    }
]


class ConfigManager:
    """配置管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.config_file = os.path.join(data_dir, "config.json")
        self.config: Dict[str, Any] = {}
        self._ensure_data_dir()
        self._load_config()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_config(self):
        """加载配置文件，不存在则创建默认配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                # 确保必要字段存在
                if "providers" not in self.config:
                    self.config["providers"] = DEFAULT_PROVIDERS
                if "current_provider" not in self.config:
                    self.config["current_provider"] = ""
                if "default_project_dir" not in self.config:
                    self.config["default_project_dir"] = ""
                if "auto_failover" not in self.config:
                    self.config["auto_failover"] = False
                if "sync_claude" not in self.config:
                    self.config["sync_claude"] = False
                if "language" not in self.config:
                    self.config["language"] = "zh"
                if "theme" not in self.config:
                    self.config["theme"] = "system"
                self._normalize_providers()
            except (json.JSONDecodeError, IOError):
                self._create_default_config()
        else:
            self._create_default_config()

    def _create_default_config(self):
        """创建默认配置"""
        self.config = {
            "providers": copy.deepcopy(DEFAULT_PROVIDERS),
            "current_provider": "",
            "default_project_dir": "",
            "auto_failover": False,
            "sync_claude": False,
            "language": "zh",
            "theme": "system"
        }
        self._normalize_providers()
        self._save_config()

    def _normalize_providers(self):
        """补齐兼容字段；内部 ID 用于把凭据与显示名称解耦。"""
        for provider in self.config.get("providers", []):
            if not provider.get("id"):
                provider["id"] = uuid.uuid4().hex
                provider["legacy_credential_name"] = provider.get("name", "")
            provider.setdefault("auth_mode", "bearer")
            provider.setdefault("provider_kind", "custom")
            provider.setdefault("enabled", True)
            provider.setdefault("priority", 99)
            provider.setdefault("is_fallback", False)

    def _save_config(self):
        """
        原子写入配置到文件
        1. 写入同目录的临时文件
        2. 原子替换（rename）
        3. 失败时回滚，不损坏原文件
        """
        try:
            # 确保目标目录存在
            os.makedirs(self.data_dir, exist_ok=True)

            # 在同目录创建临时文件（保证 rename 是原子操作）
            fd, tmp_path = tempfile.mkstemp(
                dir=self.data_dir,
                suffix=".tmp",
                prefix="config_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                # os.replace 在 Windows 上可以原子覆盖已存在的目标文件
                os.replace(tmp_path, self.config_file)
            except Exception:
                # 写入失败，清理临时文件
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                raise
        except OSError as e:
            raise IOError(f"保存配置失败: {e}") from e

    def _save_with_rollback(self, previous: Dict[str, Any]) -> bool:
        try:
            self._save_config()
            return True
        except IOError:
            self.config = previous
            return False

    def get_providers(self) -> List[Dict[str, Any]]:
        """获取所有 Provider 配置"""
        return self.config.get("providers", [])

    def get_provider(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定名称的 Provider"""
        for p in self.get_providers():
            if p.get("name") == name:
                return p
        return None

    def add_provider(self, provider: Dict[str, Any]) -> bool:
        """添加新 Provider"""
        # 检查是否已存在同名 Provider
        if self.get_provider(provider.get("name", "")):
            return False
        previous = copy.deepcopy(self.config)
        provider = copy.deepcopy(provider)
        provider.setdefault("id", uuid.uuid4().hex)
        provider.setdefault("auth_mode", "bearer")
        self.config.setdefault("providers", []).append(provider)
        return self._save_with_rollback(previous)

    def update_provider(self, name: str, provider: Dict[str, Any]) -> bool:
        """更新 Provider 配置"""
        providers = self.get_providers()
        for i, p in enumerate(providers):
            if p.get("name") == name:
                previous = copy.deepcopy(self.config)
                provider = copy.deepcopy(provider)
                provider.setdefault("id", p.get("id", uuid.uuid4().hex))
                provider.setdefault("auth_mode", p.get("auth_mode", "bearer"))
                providers[i] = provider
                self.config["providers"] = providers
                if self.config.get("current_provider") == name:
                    self.config["current_provider"] = provider.get("name", name)
                return self._save_with_rollback(previous)
        return False

    def delete_provider(self, name: str) -> bool:
        """删除 Provider"""
        providers = self.get_providers()
        original_len = len(providers)
        self.config["providers"] = [p for p in providers if p.get("name") != name]
        if len(self.config["providers"]) < original_len:
            previous = copy.deepcopy(self.config)
            previous["providers"] = providers
            # 如果删除的是当前 Provider，清空当前选择
            if self.config.get("current_provider") == name:
                self.config["current_provider"] = ""
            return self._save_with_rollback(previous)
        return False

    def get_current_provider_name(self) -> str:
        """获取当前选中的 Provider 名称"""
        return self.config.get("current_provider", "")

    def set_current_provider(self, name: str) -> bool:
        """设置当前 Provider"""
        previous = copy.deepcopy(self.config)
        self.config["current_provider"] = name
        return self._save_with_rollback(previous)

    def get_default_project_dir(self) -> str:
        """获取默认项目目录"""
        return self.config.get("default_project_dir", "")

    def set_default_project_dir(self, path: str):
        """设置默认项目目录"""
        previous = copy.deepcopy(self.config)
        self.config["default_project_dir"] = path
        return self._save_with_rollback(previous)

    def get_auto_failover(self) -> bool:
        """获取自动故障切换开关"""
        return self.config.get("auto_failover", False)

    def set_auto_failover(self, enabled: bool):
        """设置自动故障切换"""
        previous = copy.deepcopy(self.config)
        self.config["auto_failover"] = enabled
        return self._save_with_rollback(previous)

    def get_sync_claude(self) -> bool:
        """获取同步 Claude Code 配置开关"""
        return self.config.get("sync_claude", False)

    def set_sync_claude(self, enabled: bool):
        """设置同步 Claude Code 配置"""
        previous = copy.deepcopy(self.config)
        self.config["sync_claude"] = enabled
        return self._save_with_rollback(previous)

    def get_enabled_providers_sorted(self) -> List[Dict[str, Any]]:
        """获取已启用的 Provider，按优先级排序"""
        providers = [p for p in self.get_providers() if p.get("enabled", True)]
        return sorted(providers, key=lambda x: x.get("priority", 99))

    def get_language(self) -> str:
        """获取界面语言"""
        return self.config.get("language", "zh")

    def set_language(self, lang: str):
        """设置界面语言"""
        previous = copy.deepcopy(self.config)
        self.config["language"] = lang
        return self._save_with_rollback(previous)

    def get_theme(self) -> str:
        """获取主题模式：system / light / dark。"""
        value = self.config.get("theme", "system")
        return value if value in {"system", "light", "dark"} else "system"

    def set_theme(self, mode: str) -> bool:
        """保存主题模式。"""
        if mode not in {"system", "light", "dark"}:
            return False
        previous = copy.deepcopy(self.config)
        self.config["theme"] = mode
        return self._save_with_rollback(previous)

    def replace_config(self, new_config: Dict[str, Any]) -> bool:
        """用经过校验的完整配置替换当前配置。"""
        previous = copy.deepcopy(self.config)
        self.config = copy.deepcopy(new_config)
        self._normalize_providers()
        return self._save_with_rollback(previous)
