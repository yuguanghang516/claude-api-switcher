"""Provider 配置、凭据和安全验证的统一入口。"""
import copy
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .api_tester import ApiTester
from .config_manager import ConfigManager
from .credential_manager import CredentialManager


EXPORT_FIELDS = (
    "name", "base_url", "model", "small_fast_model", "enabled", "auth_mode"
)


class ProviderManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.cred = CredentialManager()
        self.tester = ApiTester()
        self._verified: Dict[str, str] = {}

    @staticmethod
    def _credential_key(provider: Dict[str, Any]) -> str:
        return provider.get("id") or provider.get("name", "")

    def _get_api_key(self, provider: Dict[str, Any]) -> str:
        key = self.cred.get_api_key(self._credential_key(provider))
        legacy_name = provider.get("legacy_credential_name")
        if not key and legacy_name:
            key = self.cred.get_api_key(legacy_name)
            if key:
                self.cred.save_api_key(self._credential_key(provider), key)
        return key

    @staticmethod
    def _fingerprint(provider: Dict[str, Any], api_key: str) -> str:
        material = "\0".join((
            provider.get("base_url", ""), provider.get("model", ""),
            provider.get("auth_mode", "bearer"), api_key,
        ))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_fields(name: str, base_url: str, model: str, priority: int) -> Tuple[bool, str]:
        if not name.strip():
            return False, "Provider 名称不能为空"
        if any(ord(ch) < 32 for ch in name + model + base_url):
            return False, "输入中不能包含控制字符"
        if not base_url.strip():
            return False, "API Base URL 不能为空"
        parsed = urlparse(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return False, "API 地址格式无效，请填写完整的 http/https 地址"
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False, "远程 API 地址必须使用 HTTPS"
        if not model.strip():
            return False, "模型名称不能为空"
        if not isinstance(priority, int) or not 1 <= priority <= 999:
            return False, "优先级必须是 1–999 的整数"
        return True, ""

    def get_all_providers(self) -> List[Dict[str, Any]]:
        result = []
        for provider in self.config.get_providers():
            item = dict(provider)
            api_key = self._get_api_key(provider)
            item["has_api_key"] = bool(api_key)
            item["masked_key"] = self.cred.mask_api_key(api_key)
            item["verified"] = self.is_verified(provider.get("name", ""))
            result.append(item)
        return result

    def get_provider_detail(self, name: str) -> Optional[Dict[str, Any]]:
        provider = self.config.get_provider(name)
        if not provider:
            return None
        item = dict(provider)
        item["api_key"] = self._get_api_key(provider)
        item["has_api_key"] = bool(item["api_key"])
        item["verified"] = self.is_verified(name)
        return item

    def add_or_update_provider(
        self, name: str, base_url: str, model: str, small_fast_model: str,
        api_key: str, enabled: bool = True, priority: int = 99,
        is_fallback: bool = False, old_name: str = "", auth_mode: str = "bearer",
    ) -> Tuple[bool, str]:
        ok, message = self._validate_fields(name, base_url, model, priority)
        if not ok:
            return False, f"{message} / Invalid provider settings"
        name = name.strip()
        base_url = base_url.strip().rstrip("/")
        model = model.strip()
        small_fast_model = small_fast_model.strip() if small_fast_model else model
        auth_mode = auth_mode if auth_mode in {"bearer", "x-api-key"} else "bearer"

        existing = self.config.get_provider(old_name) if old_name else None
        conflict = self.config.get_provider(name)
        if conflict and (not existing or conflict.get("id") != existing.get("id")):
            return False, f"已存在名为 '{name}' 的 Provider"
        if not existing and not api_key.strip():
            return False, "新增 Provider 时必须填写 API Key"

        provider_id = existing.get("id") if existing else uuid.uuid4().hex
        provider_data = {
            "id": provider_id,
            "name": name,
            "base_url": base_url,
            "model": model,
            "small_fast_model": small_fast_model,
            "enabled": bool(enabled),
            "priority": priority,
            "is_fallback": False,
            "auth_mode": auth_mode,
        }
        if existing and existing.get("legacy_credential_name"):
            provider_data["legacy_credential_name"] = existing["legacy_credential_name"]

        old_key = self._get_api_key(existing) if existing else ""
        new_key = api_key.strip() or old_key
        if not new_key:
            return False, "请填写 API Key"
        if not self.cred.save_api_key(provider_id, new_key):
            return False, "API Key 无法保存到 Windows 凭据管理器"

        saved = (self.config.update_provider(old_name, provider_data) if existing
                 else self.config.add_provider(provider_data))
        if not saved:
            if old_key:
                self.cred.save_api_key(provider_id, old_key)
            else:
                self.cred.delete_api_key(provider_id)
            return False, "配置保存失败，原配置已保留"
        self._verified.pop(provider_id, None)
        return True, "保存成功 / Saved successfully"

    def delete_provider(self, name: str) -> Tuple[bool, str]:
        provider = self.config.get_provider(name)
        if not provider:
            return False, "Provider 不存在"
        if not self.config.delete_provider(name):
            return False, "删除失败"
        self.cred.delete_api_key(self._credential_key(provider))
        self._verified.pop(self._credential_key(provider), None)
        return True, "删除成功 / Deleted successfully"

    def update_api_key(self, name: str, api_key: str) -> Tuple[bool, str]:
        provider = self.config.get_provider(name)
        if not provider or not api_key.strip():
            return False, "Provider 不存在或 API Key 为空"
        if self.cred.save_api_key(self._credential_key(provider), api_key.strip()):
            self._verified.pop(self._credential_key(provider), None)
            return True, "API Key 已更新"
        return False, "API Key 保存失败"

    def test_provider(self, name: str) -> Tuple[bool, str, int]:
        provider = self.config.get_provider(name)
        if not provider:
            return False, "Provider 不存在", 0
        if not provider.get("enabled", True):
            return False, "Provider 已禁用", 0
        api_key = self._get_api_key(provider)
        result = self.tester.test_provider(
            provider.get("base_url", ""), api_key, provider.get("model", ""),
            provider.get("auth_mode", "bearer"),
        )
        key = self._credential_key(provider)
        if result[0]:
            self._verified[key] = self._fingerprint(provider, api_key)
        else:
            self._verified.pop(key, None)
        return result

    def is_verified(self, name: str) -> bool:
        provider = self.config.get_provider(name)
        if not provider:
            return False
        api_key = self._get_api_key(provider)
        return bool(api_key) and self._verified.get(self._credential_key(provider)) == self._fingerprint(provider, api_key)

    def set_current(self, name: str) -> Tuple[bool, str]:
        provider = self.config.get_provider(name)
        if not provider:
            return False, f"Provider '{name}' 不存在"
        if not provider.get("enabled", True):
            return False, "Provider 已禁用，不能使用"
        if not self._get_api_key(provider):
            return False, "请先设置 API Key"
        if not self.is_verified(name):
            return False, "请先测试成功，再使用这个 API"
        if not self.config.set_current_provider(name):
            return False, "当前 Provider 保存失败"
        return True, f"已选择 {name}（不会修改全局 Claude 配置）"

    def get_current_provider(self) -> Optional[Dict[str, Any]]:
        name = self.config.get_current_provider_name()
        return self.get_provider_detail(name) if name else None

    def get_fallback_provider(self) -> Optional[Dict[str, Any]]:
        return None

    def export_config(self, filepath: str) -> Tuple[bool, str]:
        try:
            providers = [
                {field: provider.get(field) for field in EXPORT_FIELDS}
                for provider in self.config.get_providers()
            ]
            data = {"version": "2.2", "providers": providers,
                    "default_project_dir": self.config.get_default_project_dir()}
            with open(filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            return True, f"已导出 {len(providers)} 个 Provider（不含 API Key）"
        except Exception as exc:
            return False, f"导出失败：{str(exc)[:80]}"

    def import_config(self, filepath: str) -> Tuple[bool, str]:
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                raw = json.load(file)
            providers = raw.get("providers")
            if not isinstance(providers, list) or not 1 <= len(providers) <= 100:
                return False, "配置文件中的 Provider 列表无效"
            clean = []
            names = set()
            for item in providers:
                if not isinstance(item, dict):
                    return False, "Provider 数据格式无效"
                name = str(item.get("name", "")).strip()
                priority = 99
                ok, message = self._validate_fields(
                    name, str(item.get("base_url", "")), str(item.get("model", "")), priority)
                if not ok or name in names:
                    return False, f"导入失败：{message or 'Provider 名称重复'}"
                names.add(name)
                clean.append({
                    "id": uuid.uuid4().hex,
                    "name": name,
                    "base_url": str(item.get("base_url", "")).strip().rstrip("/"),
                    "model": str(item.get("model", "")).strip(),
                    "small_fast_model": str(item.get("small_fast_model") or item.get("model", "")).strip(),
                    "enabled": bool(item.get("enabled", True)),
                    "priority": priority,
                    "is_fallback": False,
                    "auth_mode": item.get("auth_mode") if item.get("auth_mode") in {"bearer", "x-api-key"} else "bearer",
                })
            new_config = copy.deepcopy(self.config.config)
            new_config["providers"] = clean
            new_config["current_provider"] = ""
            if isinstance(raw.get("default_project_dir"), str):
                new_config["default_project_dir"] = raw["default_project_dir"]
            new_config["auto_failover"] = False
            new_config["sync_claude"] = False
            if not self.config.replace_config(new_config):
                return False, "导入保存失败，原配置已保留"
            self._verified.clear()
            return True, f"已导入 {len(clean)} 个 Provider，请重新填写 API Key"
        except Exception as exc:
            return False, f"导入失败：{str(exc)[:80]}"
