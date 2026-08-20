"""
模型管理器
整合供应商管理、模型管理、API Key 管理

提供统一的接口供 GUI 层调用
"""
import uuid
import time
from typing import Dict, List, Optional, Tuple, Any

from .db_manager import DatabaseManager
from .gateway_server import SUPPORTED_PROVIDERS


class ModelManager:
    """模型管理器 - 统一管理层"""

    def __init__(self, db: DatabaseManager, logger=None):
        self.db = db
        self.logger = logger

    # ==================== 供应商管理 ====================

    def add_provider(self, name: str, provider_type: str, base_url: str,
                     api_key: str, auth_mode: str = "bearer",
                     models: List[Dict] = None) -> Tuple[bool, str]:
        """添加供应商"""
        if not name.strip():
            return False, "供应商名称不能为空"
        if not base_url.strip() and provider_type != "custom":
            return False, "API Base URL 不能为空"
        if not api_key.strip():
            return False, "API Key 不能为空"

        provider_id = uuid.uuid4().hex
        provider_data = {
            "id": provider_id,
            "name": name.strip(),
            "provider_type": provider_type,
            "base_url": base_url.strip().rstrip("/"),
            "api_key": api_key.strip(),
            "auth_mode": auth_mode,
            "status": "active",
        }

        ok, msg = self.db.add_provider(provider_data)
        if not ok:
            return False, msg

        # 自动添加模型
        if models:
            for m in models:
                self._add_model_to_provider(provider_id, name.strip(), m)
        elif provider_type in SUPPORTED_PROVIDERS:
            default_models = SUPPORTED_PROVIDERS[provider_type].get("models", [])
            for model_name in default_models:
                self._add_model_to_provider(provider_id, name.strip(), {"name": model_name})

        if self.logger:
            self.logger.info(f"添加供应商: {name} ({provider_type})")
        return True, "供应商添加成功"

    def _add_model_to_provider(self, provider_id: str, provider_name: str, model_info: Dict):
        """添加模型到供应商"""
        model_data = {
            "id": uuid.uuid4().hex,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "model_name": model_info.get("name", ""),
            "display_name": model_info.get("display_name", model_info.get("name", "")),
            "input_price": model_info.get("input_price", 0),
            "output_price": model_info.get("output_price", 0),
            "context_length": model_info.get("context_length", 128000),
            "status": model_info.get("status", "enabled"),
        }
        self.db.add_model(model_data)

    def update_provider(self, provider_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        """更新供应商"""
        ok, msg = self.db.update_provider(provider_id, data)
        if ok and self.logger:
            self.logger.info(f"更新供应商: {data.get('name', provider_id)}")
        return ok, msg

    def delete_provider(self, provider_id: str) -> Tuple[bool, str]:
        """删除供应商"""
        ok, msg = self.db.delete_provider(provider_id)
        if ok and self.logger:
            self.logger.info(f"删除供应商: {provider_id}")
        return ok, msg

    def get_all_providers(self) -> List[Dict[str, Any]]:
        """获取所有供应商"""
        return self.db.get_all_providers()

    def get_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取单个供应商"""
        return self.db.get_provider(provider_id)

    def get_provider_with_models(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取供应商及其模型"""
        provider = self.db.get_provider(provider_id)
        if not provider:
            return None
        provider["models"] = self.db.get_models_by_provider(provider_id)
        return provider

    # ==================== API Key 管理 ====================

    def update_api_key(self, provider_id: str, new_key: str) -> Tuple[bool, str]:
        """更新 API Key（加密存储到数据库）"""
        if not new_key.strip():
            return False, "API Key 不能为空"
        ok, msg = self.db.update_provider(provider_id, {"api_key": new_key.strip()})
        if ok and self.logger:
            self.logger.info(f"更新 API Key: {provider_id}")
        return ok, "API Key 已更新"

    def test_api_key(self, provider_id: str) -> Tuple[bool, str, int]:
        """测试 API Key 是否有效"""
        provider = self.db.get_provider(provider_id)
        if not provider:
            return False, "供应商不存在", 0

        base_url = provider.get("base_url", "")
        api_key = provider.get("api_key", "")
        auth_mode = provider.get("auth_mode", "bearer")
        provider_type = provider.get("provider_type", "custom")

        if not api_key:
            return False, "API Key 未设置", 0
        if not base_url:
            return False, "Base URL 未设置", 0

        import requests

        headers = {"Content-Type": "application/json"}
        if auth_mode == "x-api-key":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

        # 优先使用供应商已配置的模型，避免硬编码模型名导致误报
        test_model = self.db.get_models_by_provider(provider_id)
        model_name = test_model[0]["model_name"] if test_model else (
            "claude-3-5-haiku-20241022" if provider_type == "anthropic" else "gpt-4o-mini"
        )

        # 根据供应商类型选择测试端点
        if provider_type == "anthropic":
            test_url = base_url.rstrip("/")
            if not test_url.endswith("/messages"):
                test_url = f"{test_url}/messages"
        else:
            test_url = base_url.rstrip("/")
            if not test_url.endswith("/chat/completions"):
                test_url = f"{test_url}/chat/completions"

        payload = {
            "model": model_name,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "hi"}]
        }

        start = time.monotonic()
        try:
            resp = requests.post(test_url, headers=headers, json=payload, timeout=15, allow_redirects=False)
            elapsed = int((time.monotonic() - start) * 1000)

            if resp.status_code == 200:
                return True, f"连接正常 · {elapsed}ms", elapsed
            elif resp.status_code == 401:
                return False, "认证失败 · API Key 无效", elapsed
            elif resp.status_code == 403:
                return False, "无权限 · 请检查 Key 权限", elapsed
            elif resp.status_code == 429:
                return False, "请求过于频繁 · 稍后重试", elapsed
            elif resp.status_code >= 500:
                return False, f"服务不可用 · HTTP {resp.status_code}", elapsed
            else:
                return False, f"测试失败 · HTTP {resp.status_code}", elapsed
        except requests.exceptions.Timeout:
            elapsed = int((time.monotonic() - start) * 1000)
            return False, "连接超时", elapsed
        except requests.exceptions.ConnectionError:
            elapsed = int((time.monotonic() - start) * 1000)
            return False, "无法连接服务器", elapsed
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return False, f"测试异常: {str(e)[:50]}", elapsed

    # ==================== 模型管理 ====================

    def add_model(self, provider_id: str, model_name: str, display_name: str = "",
                  input_price: float = 0, output_price: float = 0,
                  context_length: int = 128000) -> Tuple[bool, str]:
        """添加模型"""
        if not model_name.strip():
            return False, "模型名称不能为空"

        provider = self.db.get_provider(provider_id)
        if not provider:
            return False, "供应商不存在"

        model_data = {
            "id": uuid.uuid4().hex,
            "provider_id": provider_id,
            "provider_name": provider.get("name", ""),
            "model_name": model_name.strip(),
            "display_name": display_name.strip() or model_name.strip(),
            "input_price": input_price,
            "output_price": output_price,
            "context_length": context_length,
            "status": "enabled",
        }
        return self.db.add_model(model_data)

    def update_model(self, model_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        """更新模型"""
        return self.db.update_model(model_id, data)

    def delete_model(self, model_id: str) -> Tuple[bool, str]:
        """删除模型"""
        return self.db.delete_model(model_id)

    def toggle_model(self, model_id: str) -> Tuple[bool, str]:
        """切换模型启用/禁用"""
        return self.db.toggle_model_status(model_id)

    def get_all_models(self) -> List[Dict[str, Any]]:
        """获取所有模型（含供应商信息）"""
        return self.db.get_all_models()

    def get_enabled_models(self) -> List[Dict[str, Any]]:
        """获取已启用模型"""
        return self.db.get_enabled_models()

    def get_models_by_provider(self, provider_id: str) -> List[Dict[str, Any]]:
        """获取供应商的模型"""
        return self.db.get_models_by_provider(provider_id)

    # ==================== 统计和日志 ====================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """获取仪表板统计"""
        return self.db.get_dashboard_stats()

    def get_today_stats(self) -> Dict[str, Any]:
        """获取今日统计"""
        return self.db.get_today_stats()

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近日志"""
        return self.db.get_recent_logs(limit)

    def get_model_stats(self) -> List[Dict[str, Any]]:
        """获取模型统计"""
        return self.db.get_model_stats()

    def get_stats_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """获取日期范围统计"""
        return self.db.get_stats_range(start_date, end_date)

    # ==================== 初始化默认数据 ====================

    def init_defaults(self):
        """初始化默认供应商和模型"""
        existing = self.db.get_all_providers()
        if existing:
            return  # 已有数据，跳过

        # 添加默认供应商
        defaults = [
            {
                "name": "OpenAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            },
            {
                "name": "Anthropic Claude",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-20241022"],
            },
            {
                "name": "DeepSeek",
                "type": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "models": ["deepseek-chat", "deepseek-reasoner"],
            },
            {
                "name": "LongCat",
                "type": "longcat",
                "base_url": "https://api.longcat.chat/openai",
                "models": ["LongCat-2.0", "LongCat-Flash-Chat"],
            },
        ]

        for p in defaults:
            provider_id = uuid.uuid4().hex
            self.db.add_provider({
                "id": provider_id,
                "name": p["name"],
                "provider_type": p["type"],
                "base_url": p["base_url"],
                "api_key": "",
                "auth_mode": "bearer",
                # 模板仅用于帮助用户快速配置；没有 Key 时不能冒充“已就绪”。
                "status": "inactive",
            })
            for m in p["models"]:
                self._add_model_to_provider(
                    provider_id, p["name"], {"name": m, "status": "disabled"})
