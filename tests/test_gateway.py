"""
V1 AI Gateway 模块测试
测试数据库管理、模型管理、网关服务器核心功能
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db_manager import DatabaseManager
from app.model_manager import ModelManager
from app.gateway_server import GatewayServer, SUPPORTED_PROVIDERS


@pytest.fixture
def db():
    """创建临时数据库（使用独立目录避免 Windows 文件锁定）"""
    tmpdir = tempfile.mkdtemp()
    try:
        database = DatabaseManager(tmpdir)
        yield database
    finally:
        database.close()
        # Windows 上 SQLite 可能延迟释放文件锁，重试删除
        import time
        for _ in range(5):
            try:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
                break
            except Exception:
                time.sleep(0.1)


@pytest.fixture
def model_mgr(db):
    """创建模型管理器"""
    return ModelManager(db)


@pytest.fixture
def gateway(db):
    """创建网关服务器"""
    return GatewayServer(db_manager=db, host="127.0.0.1", port=18787)


class TestDatabaseManager:
    """数据库管理器测试"""

    def test_init_creates_tables(self, db):
        """测试初始化创建表"""
        conn = db._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "providers" in table_names
        assert "models" in table_names
        assert "request_logs" in table_names
        assert "token_stats" in table_names

    def test_add_provider(self, db):
        """测试添加供应商"""
        ok, msg = db.add_provider({
            "id": "test-1",
            "name": "TestProvider",
            "provider_type": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test123",
        })
        assert ok is True

    def test_add_provider_duplicate(self, db):
        """测试重复供应商名称"""
        db.add_provider({"id": "test-1", "name": "TestProvider"})
        ok, msg = db.add_provider({"id": "test-2", "name": "TestProvider"})
        assert ok is False

    def test_get_provider(self, db):
        """测试获取供应商"""
        db.add_provider({"id": "test-1", "name": "TestProvider", "provider_type": "openai"})
        p = db.get_provider("test-1")
        assert p is not None
        assert p["name"] == "TestProvider"

    def test_add_model(self, db):
        """测试添加模型"""
        db.add_provider({"id": "test-1", "name": "TestProvider"})
        ok, msg = db.add_model({
            "id": "model-1",
            "provider_id": "test-1",
            "provider_name": "TestProvider",
            "model_name": "gpt-4",
        })
        assert ok is True

    def test_toggle_model(self, db):
        """测试切换模型状态"""
        db.add_provider({"id": "test-1", "name": "TestProvider"})
        db.add_model({"id": "model-1", "provider_id": "test-1", "provider_name": "TestProvider", "model_name": "gpt-4"})

        # 默认启用
        models = db.get_all_models()
        assert models[0]["status"] == "enabled"

        # 切换为禁用
        ok, msg = db.toggle_model_status("model-1")
        assert ok is True
        models = db.get_all_models()
        assert models[0]["status"] == "disabled"

    def test_log_request(self, db):
        """测试记录请求日志"""
        db.log_request({
            "model": "gpt-4",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "response_time_ms": 500,
            "status": "success",
        })
        logs = db.get_recent_logs(10)
        assert len(logs) == 1
        assert logs[0]["model"] == "gpt-4"
        assert logs[0]["total_tokens"] == 150

    def test_today_stats(self, db):
        """测试今日统计"""
        db.log_request({"model": "gpt-4", "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                       "response_time_ms": 500, "status": "success"})
        db.log_request({"model": "gpt-4", "input_tokens": 200, "output_tokens": 100, "total_tokens": 300,
                       "response_time_ms": 800, "status": "success"})

        stats = db.get_today_stats()
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 450
        assert stats["success_requests"] == 2

    def test_dashboard_stats(self, db):
        """测试仪表板统计"""
        db.add_provider({"id": "test-1", "name": "TestProvider"})
        db.add_model({"id": "model-1", "provider_id": "test-1", "provider_name": "TestProvider",
                      "model_name": "gpt-4", "status": "enabled"})

        stats = db.get_dashboard_stats()
        assert stats["model_count"] == 1
        assert stats["provider_count"] == 1


class TestModelManager:
    """模型管理器测试"""

    def test_add_provider_with_models(self, model_mgr):
        """测试添加供应商并自动添加模型"""
        ok, msg = model_mgr.add_provider(
            name="OpenAI",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
        assert ok is True

        providers = model_mgr.get_all_providers()
        assert len(providers) == 1

        models = model_mgr.get_models_by_provider(providers[0]["id"])
        assert len(models) > 0  # 自动添加了默认模型

    def test_add_custom_provider(self, model_mgr):
        """测试添加自定义供应商"""
        ok, msg = model_mgr.add_provider(
            name="MyAPI",
            provider_type="custom",
            base_url="https://my-api.com/v1",
            api_key="test-key",
            models=[{"name": "my-model"}],
        )
        assert ok is True

        models = model_mgr.get_all_models()
        assert len(models) == 1
        assert models[0]["model_name"] == "my-model"

    def test_delete_provider_cascade(self, model_mgr):
        """测试删除供应商级联删除模型"""
        model_mgr.add_provider(
            name="TestAPI", provider_type="custom",
            base_url="https://test.com/v1", api_key="key",
            models=[{"name": "m1"}, {"name": "m2"}],
        )
        providers = model_mgr.get_all_providers()
        pid = providers[0]["id"]

        ok, msg = model_mgr.delete_provider(pid)
        assert ok is True

        models = model_mgr.get_models_by_provider(pid)
        assert len(models) == 0

    def test_get_enabled_models(self, model_mgr):
        """测试获取已启用模型"""
        model_mgr.add_provider(
            name="TestAPI", provider_type="custom",
            base_url="https://test.com/v1", api_key="key",
            models=[{"name": "m1"}],
        )
        models = model_mgr.get_enabled_models()
        assert len(models) >= 1

    def test_init_defaults(self, model_mgr):
        """测试初始化默认数据"""
        model_mgr.init_defaults()
        providers = model_mgr.get_all_providers()
        assert len(providers) >= 4  # OpenAI, Anthropic, DeepSeek, LongCat

    def test_init_defaults_no_duplicate(self, model_mgr):
        """测试重复初始化不会重复添加"""
        model_mgr.init_defaults()
        model_mgr.init_defaults()
        providers = model_mgr.get_all_providers()
        names = [p["name"] for p in providers]
        assert len(names) == len(set(names))


class TestGatewayServer:
    """网关服务器测试"""

    def test_supported_providers(self):
        """测试支持的供应商配置"""
        assert "openai" in SUPPORTED_PROVIDERS
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "deepseek" in SUPPORTED_PROVIDERS
        assert "longcat" in SUPPORTED_PROVIDERS
        assert "custom" in SUPPORTED_PROVIDERS

    def test_gateway_init(self, gateway):
        """测试网关初始化"""
        assert gateway.host == "127.0.0.1"
        assert gateway.port == 18787
        assert gateway.is_running() is False

    def test_gateway_base_url(self, gateway):
        """测试网关地址"""
        assert gateway.get_base_url() == "http://127.0.0.1:18787"

    def test_gateway_start_stop(self, gateway):
        """测试启动和停止网关"""
        ok, msg = gateway.start()
        assert ok is True
        assert gateway.is_running() is True

        ok, msg = gateway.stop()
        assert ok is True
        assert gateway.is_running() is False


class TestIntegration:
    """集成测试"""

    def test_full_flow(self, model_mgr):
        """测试完整流程：添加供应商 -> 获取模型 -> 记录日志 -> 查看统计"""
        # 1. 添加供应商
        ok, msg = model_mgr.add_provider(
            name="TestOpenAI", provider_type="openai",
            base_url="https://api.openai.com/v1", api_key="sk-test",
            models=[{"name": "gpt-4o-mini"}],
        )
        assert ok is True

        # 2. 获取模型
        models = model_mgr.get_enabled_models()
        assert len(models) >= 1

        # 3. 记录日志
        model_mgr.db.log_request({
            "model": "gpt-4o-mini",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "response_time_ms": 300,
            "status": "success",
        })

        # 4. 查看统计
        stats = model_mgr.get_today_stats()
        assert stats["total_requests"] == 1
        assert stats["total_tokens"] == 150

    def test_dashboard_data(self, model_mgr):
        """测试仪表板数据"""
        model_mgr.init_defaults()
        stats = model_mgr.get_dashboard_stats()
        assert "today_requests" in stats
        assert "today_tokens" in stats
        assert "model_count" in stats
        assert "provider_count" in stats
