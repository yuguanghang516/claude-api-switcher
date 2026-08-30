"""
ConfigManager 单元测试
覆盖：加载、保存、原子写入、Provider CRUD、语言设置
"""
import os
import json
import builtins
from pathlib import Path
import pytest
from app.config_manager import ConfigManager, DEFAULT_PROVIDERS


class TestConfigManagerInit:
    """测试配置管理器初始化"""

    def test_creates_default_config_on_first_run(self, data_dir):
        """首次运行时创建默认配置"""
        config = ConfigManager(data_dir)
        assert os.path.exists(config.config_file)
        assert len(config.get_providers()) >= 1
        # 默认包含 LongCat
        names = [p["name"] for p in config.get_providers()]
        assert "LongCat" in names

    def test_default_providers_have_required_fields(self, data_dir):
        """默认 Provider 包含必要字段"""
        config = ConfigManager(data_dir)
        for p in config.get_providers():
            assert "name" in p
            assert "base_url" in p
            assert "model" in p
            assert "enabled" in p
            assert "priority" in p
            assert "is_fallback" in p

    def test_current_provider_empty_by_default(self, data_dir):
        """默认无当前 Provider"""
        config = ConfigManager(data_dir)
        assert config.get_current_provider_name() == ""

    def test_sync_claude_default_false(self, data_dir):
        """默认不覆盖 Claude Code 全局配置"""
        config = ConfigManager(data_dir)
        assert config.get_sync_claude() is False

    def test_auto_failover_default_false(self, data_dir):
        """默认关闭自动故障切换"""
        config = ConfigManager(data_dir)
        assert config.get_auto_failover() is False


class TestAtomicWrite:
    """测试原子写入"""

    def test_save_creates_valid_json(self, data_dir):
        """保存后文件是合法 JSON"""
        config = ConfigManager(data_dir)
        config.set_current_provider("LongCat")
        # 重新读取验证
        with open(config.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["current_provider"] == "LongCat"

    def test_save_preserves_existing_providers(self, data_dir):
        """保存操作不丢失已有 Provider"""
        config = ConfigManager(data_dir)
        original_count = len(config.get_providers())
        config.set_auto_failover(True)
        # 重新加载验证
        config2 = ConfigManager(data_dir)
        assert len(config2.get_providers()) == original_count

    def test_no_temp_file_left_after_save(self, data_dir):
        """保存后不留下临时文件"""
        config = ConfigManager(data_dir)
        config.set_current_provider("Test")
        # 检查数据目录中没有 .tmp 文件
        tmp_files = [f for f in os.listdir(data_dir) if f.endswith(".tmp")]
        assert len(tmp_files) == 0

    def test_corrupted_config_recreates_default(self, data_dir):
        """配置文件损坏时重建默认配置"""
        # 写入损坏的 JSON
        config_file = os.path.join(data_dir, "config.json")
        os.makedirs(data_dir, exist_ok=True)
        with open(config_file, "w") as f:
            f.write("{broken json!!!")
        # 重新初始化应恢复默认
        config = ConfigManager(data_dir)
        assert len(config.get_providers()) >= 1
        backups = list(Path(data_dir).glob("config.corrupt-*.json"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "{broken json!!!"

    @pytest.mark.parametrize("payload", [
        [],
        {"providers": {}},
        {"providers": ["not-a-provider"]},
        {"providers": [{"name": "Bad", "priority": "first"}]},
        {"providers": [{"name": "Bad", "priority": 0}]},
        {"providers": [{"name": "Bad", "priority": 1000}]},
        {"providers": [{"name": "Bad", "priority": True}]},
        {"providers": [], "theme": []},
    ])
    def test_structurally_invalid_json_is_backed_up_and_rebuilt(self, data_dir, payload):
        config_file = Path(data_dir) / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(payload), encoding="utf-8")

        config = ConfigManager(data_dir)

        assert config.get_provider("LongCat") is not None
        backups = list(Path(data_dir).glob("config.corrupt-*.json"))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text(encoding="utf-8")) == payload

    def test_legacy_provider_id_is_persisted_and_stable_across_loads(self, data_dir):
        config_file = Path(data_dir) / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        legacy = {
            "providers": [{
                "name": "Legacy",
                "base_url": "https://legacy.example.com",
                "model": "legacy-model",
            }],
        }
        config_file.write_text(json.dumps(legacy), encoding="utf-8")

        first = ConfigManager(data_dir)
        first_id = first.get_provider("Legacy")["id"]
        on_disk = json.loads(config_file.read_text(encoding="utf-8"))
        assert on_disk["providers"][0]["id"] == first_id
        assert on_disk["providers"][0]["legacy_credential_name"] == "Legacy"

        second = ConfigManager(data_dir)
        assert second.get_provider("Legacy")["id"] == first_id
        assert json.loads(config_file.read_text(encoding="utf-8")) == on_disk

    def test_read_io_error_preserves_original_config(self, data_dir, monkeypatch):
        existing = ConfigManager(data_dir)
        config_file = Path(existing.config_file)
        original = config_file.read_bytes()
        original_open = builtins.open

        def deny_config_read(path, mode="r", *args, **kwargs):
            if (os.path.abspath(os.fspath(path)) == os.path.abspath(existing.config_file)
                    and "r" in mode):
                raise PermissionError("access denied")
            return original_open(path, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", deny_config_read)
        with pytest.raises(IOError, match="读取配置失败"):
            ConfigManager(data_dir)

        assert config_file.read_bytes() == original
        assert not list(config_file.parent.glob("config.corrupt-*.json"))


class TestProviderCRUD:
    """测试 Provider 增删改"""

    def test_add_provider(self, data_dir):
        """添加新 Provider"""
        config = ConfigManager(data_dir)
        new_provider = {
            "name": "TestProvider",
            "base_url": "https://test.example.com/anthropic",
            "model": "test-model",
            "small_fast_model": "",
            "enabled": True,
            "priority": 3,
            "is_fallback": False
        }
        assert config.add_provider(new_provider) is True
        assert config.get_provider("TestProvider") is not None

    def test_add_duplicate_provider_fails(self, data_dir):
        """添加同名 Provider 失败"""
        config = ConfigManager(data_dir)
        provider = {
            "name": "LongCat",
            "base_url": "https://test.example.com",
            "model": "test",
            "small_fast_model": "",
            "enabled": True,
            "priority": 1,
            "is_fallback": False
        }
        assert config.add_provider(provider) is False

    def test_update_provider(self, data_dir):
        """更新 Provider"""
        config = ConfigManager(data_dir)
        provider = config.get_provider("LongCat")
        provider["model"] = "NewModel"
        assert config.update_provider("LongCat", provider) is True
        assert config.get_provider("LongCat")["model"] == "NewModel"

    def test_delete_provider(self, data_dir):
        """删除 Provider"""
        config = ConfigManager(data_dir)
        assert config.delete_provider("DeepSeek") is True
        assert config.get_provider("DeepSeek") is None

    def test_delete_current_clears_selection(self, data_dir):
        """删除当前 Provider 会清空选择"""
        config = ConfigManager(data_dir)
        config.set_current_provider("LongCat")
        config.delete_provider("LongCat")
        assert config.get_current_provider_name() == ""

    def test_get_enabled_providers_sorted(self, data_dir):
        """按优先级排序返回启用的 Provider"""
        config = ConfigManager(data_dir)
        providers = config.get_enabled_providers_sorted()
        priorities = [p["priority"] for p in providers]
        assert priorities == sorted(priorities)


class TestLanguageSetting:
    """测试语言设置"""

    def test_default_language_zh(self, data_dir):
        """默认语言为中文"""
        config = ConfigManager(data_dir)
        assert config.get_language() == "zh"

    def test_set_language_en(self, data_dir):
        """设置英文"""
        config = ConfigManager(data_dir)
        config.set_language("en")
        assert config.get_language() == "en"
        # 持久化验证
        config2 = ConfigManager(data_dir)
        assert config2.get_language() == "en"
