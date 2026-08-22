"""
ProviderManager 单元测试
使用 mock 凭据管理器
"""
import os
import json
import pytest
from app.config_manager import ConfigManager
from app.provider_manager import ProviderManager


class TestProviderManager:
    """Provider 管理器测试"""

    @pytest.fixture
    def manager(self, data_dir, monkeypatch):
        """创建带 mock 凭据的 ProviderManager"""
        store = {}

        def mock_save(service, key, value):
            store[(service, key)] = value
            return True

        def mock_get(service, key):
            return store.get((service, key), "")

        def mock_delete(service, key):
            store.pop((service, key), None)
            return True

        import app.credential_manager as cred_mod
        monkeypatch.setattr(cred_mod.keyring, "set_password", mock_save)
        monkeypatch.setattr(cred_mod.keyring, "get_password",
                            lambda s, k: mock_get(s, k))
        monkeypatch.setattr(cred_mod.keyring, "delete_password", mock_delete)

        config = ConfigManager(data_dir)
        return ProviderManager(config), store

    def test_get_all_providers_includes_key_info(self, manager):
        """获取所有 Provider 包含 Key 信息"""
        mgr, store = manager
        providers = mgr.get_all_providers()
        assert len(providers) > 0
        for p in providers:
            assert "has_api_key" in p
            assert "masked_key" in p

    def test_add_new_provider(self, manager):
        """添加新 Provider"""
        mgr, store = manager
        success, msg = mgr.add_or_update_provider(
            name="TestAPI",
            base_url="https://test.example.com/anthropic",
            model="test-model",
            small_fast_model="",
            api_key="sk-test1234567890abcdef",
            enabled=True,
            priority=5,
            is_fallback=False
        )
        assert success is True
        assert mgr.config.get_provider("TestAPI") is not None

    def test_gcli2api_kind_is_preserved(self, manager):
        """gcli2api 专用类型可保存，并随无密钥导出保留。"""
        mgr, _ = manager
        success, _ = mgr.add_or_update_provider(
            name="Gemini CLI (gcli2api)",
            base_url="http://127.0.0.1:7861",
            model="gemini-2.5-pro",
            small_fast_model="gemini-2.5-flash",
            api_key="local-password",
            provider_kind="gcli2api",
        )
        assert success is True
        assert mgr.config.get_provider("Gemini CLI (gcli2api)")["provider_kind"] == "gcli2api"

    def test_add_provider_missing_name_fails(self, manager):
        """缺少名称时添加失败"""
        mgr, store = manager
        success, msg = mgr.add_or_update_provider(
            name="",
            base_url="https://test.example.com/anthropic",
            model="test-model",
            small_fast_model="",
            api_key="sk-test",
        )
        assert success is False

    def test_add_provider_missing_url_fails(self, manager):
        """缺少 URL 时添加失败"""
        mgr, store = manager
        success, msg = mgr.add_or_update_provider(
            name="Test",
            base_url="",
            model="test-model",
            small_fast_model="",
            api_key="sk-test",
        )
        assert success is False

    def test_add_provider_missing_model_fails(self, manager):
        """缺少模型名时添加失败"""
        mgr, store = manager
        success, msg = mgr.add_or_update_provider(
            name="Test",
            base_url="https://test.example.com/anthropic",
            model="",
            small_fast_model="",
            api_key="sk-test",
        )
        assert success is False

    def test_add_duplicate_name_fails(self, manager):
        """添加同名 Provider 失败"""
        mgr, store = manager
        success, msg = mgr.add_or_update_provider(
            name="LongCat",
            base_url="https://other.example.com",
            model="other-model",
            small_fast_model="",
            api_key="sk-other",
        )
        assert success is False

    def test_update_provider(self, manager):
        """更新 Provider"""
        mgr, store = manager
        success, msg = mgr.add_or_update_provider(
            name="LongCat",
            base_url="https://new-url.example.com/anthropic",
            model="new-model",
            small_fast_model="",
            api_key="sk-newkey1234567890",
            old_name="LongCat"
        )
        assert success is True
        provider = mgr.config.get_provider("LongCat")
        assert provider["base_url"] == "https://new-url.example.com/anthropic"
        assert provider["model"] == "new-model"

    def test_delete_provider(self, manager):
        """删除 Provider"""
        mgr, store = manager
        # 先设置 key
        mgr.add_or_update_provider(
            name="ToDelete",
            base_url="https://delete.example.com/anthropic",
            model="delete-model",
            small_fast_model="",
            api_key="sk-todelete1234567890",
        )
        success, msg = mgr.delete_provider("ToDelete")
        assert success is True
        assert mgr.config.get_provider("ToDelete") is None

    def test_set_current_provider(self, manager):
        """设置当前 Provider"""
        mgr, store = manager
        # 先为 LongCat 设置 key
        mgr.add_or_update_provider(
            name="LongCat",
            base_url="https://api.longcat.chat/anthropic",
            model="LongCat-2.0",
            small_fast_model="",
            api_key="sk-longcat1234567890",
            old_name="LongCat"
        )
        mgr.tester.test_provider = lambda *args, **kwargs: (True, "正常", 1)
        assert mgr.test_provider("LongCat")[0] is True
        success, msg = mgr.set_current("LongCat")
        assert success is True
        assert mgr.config.get_current_provider_name() == "LongCat"

    def test_set_current_without_key_fails(self, manager):
        """没有 Key 时设置当前失败"""
        mgr, store = manager
        # DeepSeek 默认没有 key
        success, msg = mgr.set_current("DeepSeek")
        assert success is False

    def test_get_current_provider_detail(self, manager):
        """获取当前 Provider 详情"""
        mgr, store = manager
        mgr.add_or_update_provider(
            name="LongCat",
            base_url="https://api.longcat.chat/anthropic",
            model="LongCat-2.0",
            small_fast_model="",
            api_key="sk-longcat1234567890",
            old_name="LongCat"
        )
        mgr.tester.test_provider = lambda *args, **kwargs: (True, "正常", 1)
        mgr.test_provider("LongCat")
        mgr.set_current("LongCat")
        current = mgr.get_current_provider()
        assert current is not None
        assert current["name"] == "LongCat"
        assert current["api_key"] == "sk-longcat1234567890"

    def test_fake_fallback_feature_is_removed(self, manager):
        """未实现的自动故障切换不再对用户作出承诺"""
        mgr, store = manager
        # 为 DeepSeek 设置 key（保留 is_fallback=True）
        mgr.add_or_update_provider(
            name="DeepSeek",
            base_url="https://api.deepseek.com/anthropic",
            model="deepseek-chat",
            small_fast_model="",
            api_key="sk-deepseek1234567890",
            is_fallback=True,
            old_name="DeepSeek"
        )
        fallback = mgr.get_fallback_provider()
        assert fallback is None

    def test_api_key_saved_to_credential_store(self, manager):
        """API Key 保存到凭据管理器"""
        mgr, store = manager
        mgr.add_or_update_provider(
            name="KeyTest",
            base_url="https://keytest.example.com/anthropic",
            model="keytest-model",
            small_fast_model="",
            api_key="sk-mytestkey1234567890",
        )
        # 凭据按不可伪造的内部 ID 保存，不再按可重名的显示名称绑定
        provider_id = mgr.config.get_provider("KeyTest")["id"]
        assert ("ClaudeAPISwitcher", provider_id) in store
        assert store[("ClaudeAPISwitcher", provider_id)] == "sk-mytestkey1234567890"

    def test_api_key_not_in_config_file(self, manager):
        """API Key 不应明文出现在配置文件中"""
        mgr, store = manager
        mgr.add_or_update_provider(
            name="SecretTest",
            base_url="https://secret.example.com/anthropic",
            model="secret-model",
            small_fast_model="",
            api_key="sk-supersecret999999999",
        )
        # 读取配置文件
        with open(mgr.config.config_file, "r", encoding="utf-8") as f:
            config_content = f.read()
        # 完整 key 不应出现在配置文件中
        assert "sk-supersecret999999999" not in config_content

    def test_export_config_excludes_keys(self, manager, temp_dir):
        """导出配置不包含 API Key"""
        mgr, store = manager
        mgr.add_or_update_provider(
            name="ExportTest",
            base_url="https://export.example.com/anthropic",
            model="export-model",
            small_fast_model="",
            api_key="sk-exportsecret1234567890",
        )
        export_path = os.path.join(temp_dir, "export.json")
        success, msg = mgr.export_config(export_path)
        assert success is True
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "sk-exportsecret1234567890" not in json.dumps(data)
