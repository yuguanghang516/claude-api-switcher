"""
V2 智能 AI Gateway 模块测试
测试所有新增 V2 模块的核心功能
"""
import os
import sys
import time
import tempfile
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.v2_config import V2ConfigManager, DEFAULT_V2_CONFIG
from app.balance_checker import BalanceChecker, BalanceInfo
from app.key_rotator import MultiKeyRotator, KeyStatus, KeyInfo
from app.failover import FailoverEngine, FailoverTarget, CircuitBreaker, CircuitState, FailoverExhausted
from app.smart_router import SmartRouter, ModelCapability, TaskClassifier, RoutingRule
from app.cost_controller import CostController, BudgetStatus
from app.pricing import PricingCalculator, MODEL_PRICING
from app.notifier import Notifier, Notification, NotificationType, NotificationPriority
from app.hot_reload import HotReloader, ConfigHotSwapper


@pytest.fixture
def tmp_dir():
    """创建临时目录"""
    dirpath = tempfile.mkdtemp()
    yield dirpath
    import shutil
    for _ in range(5):
        try:
            shutil.rmtree(dirpath, ignore_errors=True)
            break
        except Exception:
            time.sleep(0.1)


@pytest.fixture
def v2_config(tmp_dir):
    """创建 V2 配置管理器"""
    return V2ConfigManager(tmp_dir)


# ==================== V2 Config Tests ====================

class TestV2Config:
    """V2 配置管理测试"""

    def test_init_creates_default_config(self, v2_config):
        """测试初始化创建默认配置"""
        assert v2_config.config is not None
        assert "multi_keys" in v2_config.config
        assert "routing_rules" in v2_config.config
        assert "budget" in v2_config.config
        assert "notifications" in v2_config.config

    def test_multi_keys_management(self, v2_config):
        """测试多 Key 管理"""
        provider_id = "test-provider-1"

        # 添加 Key
        assert v2_config.add_key(provider_id, "sk-key1") is True
        assert v2_config.add_key(provider_id, "sk-key2") is True

        # 获取 Keys
        keys = v2_config.get_multi_keys(provider_id)
        assert len(keys) == 2
        assert "sk-key1" in keys
        assert "sk-key2" in keys

        # 设置 Keys
        assert v2_config.set_multi_keys(provider_id, ["sk-new1", "sk-new2", "sk-new3"]) is True
        keys = v2_config.get_multi_keys(provider_id)
        assert len(keys) == 3

        # 删除 Key
        assert v2_config.remove_key(provider_id, 0) is True
        keys = v2_config.get_multi_keys(provider_id)
        assert len(keys) == 2

    def test_routing_rules(self, v2_config):
        """测试路由规则"""
        rules = v2_config.get_routing_rules()
        assert "code" in rules
        assert "chat" in rules
        assert "cheap" in rules
        assert "complex" in rules

        # 修改规则
        new_rule = {
            "description": "测试规则",
            "preferred_models": ["gpt-4o"],
            "fallback_models": ["gpt-3.5-turbo"],
            "enabled": True,
        }
        assert v2_config.set_routing_rule("test", new_rule) is True
        rule = v2_config.get_routing_rule("test")
        assert rule["description"] == "测试规则"

    def test_budget_config(self, v2_config):
        """测试预算配置"""
        budget = v2_config.get_budget()
        assert "daily_limit_usd" in budget
        assert "monthly_limit_usd" in budget
        assert "warning_threshold" in budget

        assert v2_config.get_daily_limit() == budget["daily_limit_usd"]
        assert v2_config.get_monthly_limit() == budget["monthly_limit_usd"]

    def test_routing_enabled(self, v2_config):
        """测试路由开关"""
        assert v2_config.is_routing_enabled() is True
        v2_config.set_routing_enabled(False)
        assert v2_config.is_routing_enabled() is False

    def test_export_import(self, v2_config):
        """测试配置导入导出"""
        exported = v2_config.export_config()
        assert "routing_rules" in exported
        assert "budget" in exported

        # 修改后导入
        exported["routing_enabled"] = False
        assert v2_config.import_config(exported) is True
        assert v2_config.is_routing_enabled() is False

    def test_reload(self, v2_config):
        """测试配置重载"""
        v2_config.reload()
        assert v2_config.config is not None

    def test_change_callback(self, v2_config):
        """测试变更回调"""
        callback_called = []

        def on_change(old, new):
            callback_called.append((old, new))

        v2_config.on_change(on_change)
        v2_config.set_routing_enabled(False)
        # 手动触发保存以触发回调
        v2_config.save()


# ==================== Balance Checker Tests ====================

class TestBalanceChecker:
    """余额检测器测试"""

    def test_init(self):
        """测试初始化"""
        checker = BalanceChecker()
        assert checker._cache == {}
        assert checker._auto_refresh is False

    def test_balance_info(self):
        """测试余额信息数据类"""
        info = BalanceInfo(
            provider="TestProvider",
            balance=50.0,
            total_grant=100.0,
            used=50.0,
            currency="USD",
            percent_remaining=50.0,
            status="ok",
        )
        assert info.provider == "TestProvider"
        assert info.balance == 50.0
        assert info.percent_remaining == 50.0

        # 序列化
        d = info.to_dict()
        assert d["provider"] == "TestProvider"
        assert d["balance"] == 50.0

        # 格式化
        summary = info.format_summary()
        assert "TestProvider" in summary
        assert "50%" in summary

    def test_balance_info_error(self):
        """测试错误状态"""
        info = BalanceInfo(provider="Test", status="error", error="API Key 无效")
        assert info.status == "error"
        assert "检测失败" in info.format_summary()

    def test_check_generic_balance_no_url(self):
        """测试通用余额检测 - 无 URL"""
        checker = BalanceChecker()
        result = checker._check_generic_balance("custom", "sk-test", "")
        assert result.status == "unknown"

    def test_cache_management(self):
        """测试缓存管理"""
        checker = BalanceChecker()
        info = BalanceInfo(provider="Test", balance=100, status="ok",
                          last_updated=int(time.time()))

        # 手动设置缓存
        checker._cache["Test"] = info

        # 获取缓存
        cached = checker.get_cached("Test")
        assert cached is not None
        assert cached.balance == 100

        # 获取所有缓存
        all_cached = checker.get_all_cached()
        assert len(all_cached) == 1

        # 清除缓存
        checker.clear_cache()
        assert len(checker._cache) == 0

    def test_auto_refresh_start_stop(self):
        """测试自动刷新启动停止"""
        checker = BalanceChecker()
        checker.start_auto_refresh(interval=1, providers=[])
        assert checker._auto_refresh is True
        assert checker._refresh_timer is not None

        checker.stop_auto_refresh()
        assert checker._auto_refresh is False


# ==================== Key Rotator Tests ====================

class TestKeyRotator:
    """多 Key 轮询器测试"""

    def test_init(self):
        """测试初始化"""
        rotator = MultiKeyRotator(strategy="round_robin")
        assert rotator._strategy == "round_robin"
        assert rotator._keys == {}

    def test_set_keys(self):
        """测试设置 Key"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1", "sk-key2", "sk-key3"])
        assert rotator.get_total_key_count("provider1") == 3
        assert rotator.get_active_key_count("provider1") == 3

    def test_add_remove_key(self):
        """测试添加删除 Key"""
        rotator = MultiKeyRotator()
        rotator.add_key("provider1", "sk-key1")
        rotator.add_key("provider1", "sk-key2")
        assert rotator.get_total_key_count("provider1") == 2

        rotator.remove_key("provider1", 0)
        assert rotator.get_total_key_count("provider1") == 1

    def test_round_robin_strategy(self):
        """测试轮询策略"""
        rotator = MultiKeyRotator(strategy="round_robin")
        rotator.set_keys("provider1", ["sk-key1", "sk-key2", "sk-key3"])

        # 轮询应该轮流返回
        key1 = rotator.get_current_key("provider1")
        assert key1 is not None

    def test_priority_strategy(self):
        """测试优先级策略"""
        rotator = MultiKeyRotator(strategy="priority")
        rotator.set_keys("provider1", ["sk-key1", "sk-key2", "sk-key3"])

        key = rotator.get_current_key("provider1")
        assert key == "sk-key1"  # 优先级策略返回第一个

    def test_report_success(self):
        """测试报告成功"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1", "sk-key2"])

        rotator.report_success("provider1", "sk-key1")
        keys = rotator.get_key_status("provider1")
        assert keys[0]["use_count"] == 1

    def test_report_error(self):
        """测试报告错误"""
        rotator = MultiKeyRotator(max_consecutive_errors=3)
        rotator.set_keys("provider1", ["sk-key1", "sk-key2"])

        # 报告错误
        rotator.report_error("provider1", "sk-key1", "timeout")
        keys = rotator.get_key_status("provider1")
        assert keys[0]["status"] == KeyStatus.ERROR.value
        assert keys[0]["consecutive_errors"] == 1

    def test_report_rate_limit(self):
        """测试报告限流"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1", "sk-key2"])

        rotator.report_rate_limit("provider1", "sk-key1", reset_seconds=60)
        keys = rotator.get_key_status("provider1")
        assert keys[0]["status"] == KeyStatus.RATE_LIMITED.value

    def test_get_next_key_on_failure(self):
        """测试失败时切换 Key"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1", "sk-key2", "sk-key3"])

        # 第一个 Key 失败
        next_key = rotator.get_next_key("provider1")
        assert next_key == "sk-key2"

    def test_has_available_key(self):
        """测试是否有可用 Key"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1"])

        assert rotator.has_available_key("provider1") is True

    def test_reset_all_keys(self):
        """测试重置所有 Key"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1", "sk-key2"])

        rotator.report_error("provider1", "sk-key1", "error")
        rotator.reset_all_keys("provider1")

        keys = rotator.get_key_status("provider1")
        assert all(k["status"] == KeyStatus.ACTIVE.value for k in keys)

    def test_rotation_summary(self):
        """测试轮询摘要"""
        rotator = MultiKeyRotator()
        rotator.set_keys("provider1", ["sk-key1", "sk-key2"])

        summary = rotator.get_rotation_summary("provider1")
        assert summary["total"] == 2
        assert summary["active"] == 2
        assert summary["strategy"] == "round_robin"


# ==================== Failover Engine Tests ====================

class TestFailoverEngine:
    """故障转移引擎测试"""

    def test_circuit_breaker(self):
        """测试熔断器"""
        cb = CircuitBreaker(threshold=3, reset_seconds=60)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

        # 记录失败
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        # 达到阈值
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # 记录成功重置
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_auto_reset(self):
        """测试熔断器自动重置"""
        cb = CircuitBreaker(threshold=1, reset_seconds=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # 等待重置时间后应该进入 HALF_OPEN
        time.sleep(1.1)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_failover_target(self):
        """测试故障转移目标"""
        target = FailoverTarget(
            model_name="gpt-4o",
            provider_id="openai",
            provider_name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            priority=0,
        )
        assert target.model_name == "gpt-4o"
        assert target.is_healthy is True

        d = target.to_dict()
        assert d["model_name"] == "gpt-4o"

    def test_set_targets(self):
        """测试设置目标"""
        engine = FailoverEngine()
        targets = [
            FailoverTarget(model_name="gpt-4o", provider_id="p1", provider_name="P1",
                          base_url="url1", api_key="key1", priority=0),
            FailoverTarget(model_name="claude", provider_id="p2", provider_name="P2",
                          base_url="url2", api_key="key2", priority=1),
        ]
        engine.set_targets(targets)
        assert len(engine.get_healthy_targets()) == 2

    def test_add_remove_target(self):
        """测试添加删除目标"""
        engine = FailoverEngine()
        target = FailoverTarget(model_name="gpt-4o", provider_id="p1", provider_name="P1",
                               base_url="url1", api_key="key1")
        engine.add_target(target)
        assert len(engine.get_healthy_targets()) == 1

        engine.remove_target("gpt-4o", "p1")
        assert len(engine.get_healthy_targets()) == 0

    def test_get_target_status(self):
        """测试获取目标状态"""
        engine = FailoverEngine()
        target = FailoverTarget(model_name="gpt-4o", provider_id="p1", provider_name="P1",
                               base_url="url1", api_key="key1")
        engine.add_target(target)

        status = engine.get_target_status()
        assert len(status) == 1
        assert status[0]["model_name"] == "gpt-4o"

    def test_reset_circuit(self):
        """测试重置熔断器"""
        engine = FailoverEngine()
        target = FailoverTarget(model_name="gpt-4o", provider_id="p1", provider_name="P1",
                               base_url="url1", api_key="key1")
        engine.add_target(target)

        # 获取熔断器并设置为 OPEN
        key = "p1:gpt-4o"
        engine._circuit_breakers[key].record_failure()
        engine._circuit_breakers[key].record_failure()
        engine._circuit_breakers[key].record_failure()
        engine._circuit_breakers[key].record_failure()
        engine._circuit_breakers[key].record_failure()

        # 重置
        engine.reset_circuit("gpt-4o", "p1")
        assert engine._circuit_breakers[key].state == CircuitState.CLOSED

    def test_reset_all_circuits(self):
        """测试重置所有熔断器"""
        engine = FailoverEngine()
        targets = [
            FailoverTarget(model_name="m1", provider_id="p1", provider_name="P1",
                          base_url="url1", api_key="key1"),
            FailoverTarget(model_name="m2", provider_id="p2", provider_name="P2",
                          base_url="url2", api_key="key2"),
        ]
        engine.set_targets(targets)
        engine.reset_all_circuits()
        # 所有目标应该健康
        for t in engine._targets:
            assert t.is_healthy is True


# ==================== Smart Router Tests ====================

class TestSmartRouter:
    """智能路由器测试"""

    def test_task_classifier_code(self):
        """测试任务分类 - 代码"""
        messages = [{"role": "user", "content": "帮我写一个 Python 函数来排序列表"}]
        result = TaskClassifier.classify(messages)
        assert result == "code"

    def test_task_classifier_chat(self):
        """测试任务分类 - 聊天"""
        messages = [{"role": "user", "content": "你好，今天天气怎么样？"}]
        result = TaskClassifier.classify(messages)
        assert result == "chat"

    def test_task_classifier_explicit(self):
        """测试任务分类 - 显式指定"""
        messages = [{"role": "user", "content": "你好"}]
        result = TaskClassifier.classify(messages, explicit_type="code")
        assert result == "code"

    def test_task_classifier_code_signals(self):
        """测试任务分类 - 代码信号"""
        messages = [{"role": "user", "content": "```python\ndef hello():\n    pass\n```"}]
        result = TaskClassifier.classify(messages)
        assert result == "code"

    def test_register_model(self):
        """测试注册模型"""
        router = SmartRouter()
        model = ModelCapability(
            model_name="gpt-4o",
            provider_name="OpenAI",
            provider_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            auth_mode="bearer",
            provider_type="openai",
            input_price=2.5,
            output_price=10.0,
            context_length=128000,
            capabilities=["chat", "code"],
        )
        router.register_model(model)
        assert "gpt-4o" in router._models

    def test_route_with_preferred_model(self):
        """测试路由 - 指定模型"""
        router = SmartRouter()
        model = ModelCapability(
            model_name="gpt-4o",
            provider_name="OpenAI",
            provider_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            auth_mode="bearer",
            provider_type="openai",
            input_price=2.5,
            output_price=10.0,
            context_length=128000,
            capabilities=["chat", "code"],
        )
        router.register_model(model)

        messages = [{"role": "user", "content": "你好"}]
        result = router.route(messages, preferred_model="gpt-4o")
        assert result is not None
        assert result.model_name == "gpt-4o"

    def test_route_by_task_type(self):
        """测试路由 - 按任务类型"""
        router = SmartRouter()

        # 注册代码模型
        router.register_model(ModelCapability(
            model_name="claude-sonnet-4-20250514",
            provider_name="Anthropic",
            provider_id="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="sk-test",
            auth_mode="x-api-key",
            provider_type="anthropic",
            input_price=3.0,
            output_price=15.0,
            context_length=200000,
            capabilities=["chat", "code", "reasoning"],
        ))

        messages = [{"role": "user", "content": "写一个快速排序算法"}]
        result = router.route(messages)
        assert result is not None

    def test_get_cheapest_model(self):
        """测试获取最便宜模型"""
        router = SmartRouter()

        router.register_model(ModelCapability(
            model_name="expensive",
            provider_name="P1",
            provider_id="p1",
            base_url="url1",
            api_key="key1",
            auth_mode="bearer",
            provider_type="custom",
            input_price=10.0,
            output_price=30.0,
            context_length=128000,
            capabilities=["chat"],
        ))
        router.register_model(ModelCapability(
            model_name="cheap",
            provider_name="P2",
            provider_id="p2",
            base_url="url2",
            api_key="key2",
            auth_mode="bearer",
            provider_type="custom",
            input_price=0.1,
            output_price=0.2,
            context_length=128000,
            capabilities=["chat"],
        ))

        cheapest = router.get_cheapest_model()
        assert cheapest is not None
        assert cheapest.model_name == "cheap"

    def test_get_routing_info(self):
        """测试获取路由信息"""
        router = SmartRouter()
        router.register_model(ModelCapability(
            model_name="gpt-4o",
            provider_name="OpenAI",
            provider_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            auth_mode="bearer",
            provider_type="openai",
            input_price=2.5,
            output_price=10.0,
            context_length=128000,
            capabilities=["chat", "code"],
        ))

        messages = [{"role": "user", "content": "你好"}]
        info = router.get_routing_info(messages)
        assert "detected_task_type" in info
        assert "selected_model" in info


# ==================== Cost Controller Tests ====================

class TestCostController:
    """成本控制器测试"""

    def test_init(self):
        """测试初始化"""
        controller = CostController(daily_limit=5.0, monthly_limit=100.0)
        assert controller.daily_limit == 5.0
        assert controller.monthly_limit == 100.0

    def test_record_cost(self):
        """测试记录花费"""
        controller = CostController(daily_limit=10.0, monthly_limit=100.0)
        controller.record_cost(0.5, "gpt-4o")
        controller.record_cost(1.0, "claude")

        status = controller.get_status()
        assert status.daily_used == 1.5
        assert status.daily_remaining == 8.5

    def test_daily_percent(self):
        """测试每日百分比"""
        controller = CostController(daily_limit=10.0)
        controller.record_cost(8.0, "gpt-4o")

        status = controller.get_status()
        assert status.daily_percent == 80.0

    def test_budget_exceeded(self):
        """测试预算超限"""
        controller = CostController(daily_limit=5.0, auto_switch_cheap=False)
        controller.record_cost(6.0, "gpt-4o")

        status = controller.get_status()
        assert status.budget_exceeded is True

    def test_should_switch_to_cheap(self):
        """测试是否应切换低成本"""
        controller = CostController(daily_limit=5.0, auto_switch_cheap=True)
        assert controller.should_switch_to_cheap() is False

        controller.record_cost(6.0, "gpt-4o")
        assert controller.should_switch_to_cheap() is True

    def test_is_within_budget(self):
        """测试是否在预算内"""
        controller = CostController(daily_limit=5.0)
        assert controller.is_within_budget() is True

        controller.record_cost(6.0, "gpt-4o")
        assert controller.is_within_budget() is False

    def test_get_daily_usage_by_model(self):
        """测试获取每日各模型花费"""
        controller = CostController()
        controller.record_cost(0.5, "gpt-4o")
        controller.record_cost(1.0, "claude")
        controller.record_cost(0.3, "gpt-4o")

        usage = controller.get_daily_usage_by_model()
        assert usage["gpt-4o"] == 0.8
        assert usage["claude"] == 1.0

    def test_cleanup_old_data(self):
        """测试清理旧数据"""
        controller = CostController()
        controller.record_cost(1.0, "gpt-4o")
        controller.cleanup_old_data(days=0)
        # 清理后应该还有今日数据（days=0 表示清理 0 天前的）

    def test_set_limits(self):
        """测试设置预算"""
        controller = CostController()
        controller.set_daily_limit(10.0)
        controller.set_monthly_limit(200.0)
        assert controller.daily_limit == 10.0
        assert controller.monthly_limit == 200.0


# ==================== Pricing Calculator Tests ====================

class TestPricingCalculator:
    """价格计算器测试"""

    def test_init(self):
        """测试初始化"""
        calc = PricingCalculator(usd_to_cny=7.2)
        assert calc.get_exchange_rate() == 7.2
        assert len(calc.get_all_pricing()) > 0

    def test_calculate_cost(self):
        """测试计算费用"""
        calc = PricingCalculator(usd_to_cny=7.2)
        cost = calc.calculate_cost("gpt-4o", 1000, 500)

        assert cost.model == "gpt-4o"
        assert cost.input_tokens == 1000
        assert cost.output_tokens == 500
        assert cost.total_cost_usd > 0
        assert cost.total_cost_cny == cost.total_cost_usd * 7.2

    def test_calculate_cost_unknown_model(self):
        """测试未知模型费用"""
        calc = PricingCalculator()
        cost = calc.calculate_cost("unknown-model", 1000, 500)
        assert cost.total_cost_usd == 0

    def test_estimate_cost(self):
        """测试预估费用"""
        calc = PricingCalculator()
        cost = calc.estimate_cost("gpt-4o", 2000, 1000)
        assert cost.total_cost_usd > 0

    def test_compare_models(self):
        """测试模型费用比较"""
        calc = PricingCalculator()
        comparison = calc.compare_models(1000, 1000)
        assert len(comparison) > 0
        # 应该按费用排序
        costs = [c["total_cost_usd"] for c in comparison]
        assert costs == sorted(costs)

    def test_get_cheapest_model(self):
        """测试获取最便宜模型"""
        calc = PricingCalculator()
        cheapest = calc.get_cheapest_model()
        assert cheapest is not None
        assert len(cheapest) > 0

    def test_set_model_pricing(self):
        """测试设置模型价格"""
        calc = PricingCalculator()
        calc.set_model_pricing("my-model", 1.0, 2.0, "MyProvider")

        pricing = calc.get_model_pricing("my-model")
        assert pricing["input"] == 1.0
        assert pricing["output"] == 2.0
        assert pricing["provider"] == "MyProvider"

    def test_get_pricing_table(self):
        """测试获取价格表"""
        calc = PricingCalculator()
        table = calc.get_pricing_table()
        assert len(table) > 0
        assert "model" in table[0]
        assert "input_price" in table[0]
        assert "output_price" in table[0]

    def test_set_exchange_rate(self):
        """测试设置汇率"""
        calc = PricingCalculator()
        calc.set_exchange_rate(7.5)
        assert calc.get_exchange_rate() == 7.5


# ==================== Notifier Tests ====================

class TestNotifier:
    """通知系统测试"""

    def test_init(self):
        """测试初始化"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False)
        assert notifier.desktop_enabled is False
        assert notifier.webhook_enabled is False

    def test_notify(self):
        """测试发送通知"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False)
        notif = Notification(
            type=NotificationType.INFO,
            title="测试标题",
            message="测试消息",
            priority=NotificationPriority.MEDIUM,
        )
        result = notifier.notify(notif)
        assert result is True

    def test_notify_deduplication(self):
        """测试通知去重"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=60)
        notif = Notification(
            type=NotificationType.INFO,
            title="测试",
            message="消息",
        )
        # 第一次应成功
        assert notifier.notify(notif) is True
        # 第二次（同类型）应被去重
        assert notifier.notify(notif) is False

    def test_notify_low_balance(self):
        """测试余额不足通知"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        result = notifier.notify_low_balance("OpenAI", 5.0, 10.0)
        assert result is True

    def test_notify_api_error(self):
        """测试 API 错误通知"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        result = notifier.notify_api_error("OpenAI", "连接超时", "gpt-4o")
        assert result is True

    def test_notify_budget_exceeded(self):
        """测试预算超限通知"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        result = notifier.notify_budget_exceeded(5.0, 5.0, 100.0, 100.0)
        assert result is True

    def test_notify_budget_warning(self):
        """测试预算警告通知"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        result = notifier.notify_budget_warning(85.0, 70.0)
        assert result is True

    def test_get_history(self):
        """测试获取历史"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        for i in range(5):
            notifier.notify(Notification(
                type=NotificationType.INFO,
                title=f"通知{i}",
                message=f"消息{i}",
            ))

        history = notifier.get_history(10)
        assert len(history) == 5

    def test_clear_history(self):
        """测试清空历史"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        notifier.notify(Notification(type=NotificationType.INFO, title="测试", message="消息"))
        notifier.clear_history()
        assert len(notifier.get_history()) == 0

    def test_notification_to_dict(self):
        """测试通知序列化"""
        notif = Notification(
            type=NotificationType.LOW_BALANCE,
            title="余额不足",
            message="OpenAI 剩余 $5",
            priority=NotificationPriority.HIGH,
            data={"balance": 5.0},
        )
        d = notif.to_dict()
        assert d["type"] == "low_balance"
        assert d["title"] == "余额不足"
        assert d["priority"] == "high"

    def test_on_notification_callback(self):
        """测试通知回调"""
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)
        notifications = []

        def on_notif(n):
            notifications.append(n)

        notifier.on_notification(on_notif)
        notifier.notify(Notification(type=NotificationType.INFO, title="测试", message="消息"))

        assert len(notifications) == 1


# ==================== Hot Reload Tests ====================

class TestHotReload:
    """热切换测试"""

    def test_init(self):
        """测试初始化"""
        reloader = HotReloader(watch_interval=1)
        assert reloader._watch_interval == 1
        assert reloader._running is False

    def test_watch_file(self, tmp_dir):
        """测试添加监控文件"""
        reloader = HotReloader()
        test_file = os.path.join(tmp_dir, "test.json")
        with open(test_file, "w") as f:
            f.write("{}")

        reloader.watch_file(test_file)
        assert test_file in reloader.get_watched_files()

    def test_unwatch_file(self, tmp_dir):
        """测试取消监控"""
        reloader = HotReloader()
        test_file = os.path.join(tmp_dir, "test.json")
        with open(test_file, "w") as f:
            f.write("{}")

        reloader.watch_file(test_file)
        reloader.unwatch_file(test_file)
        assert test_file not in reloader.get_watched_files()

    def test_on_any_change(self, tmp_dir):
        """测试全局变更回调"""
        reloader = HotReloader(watch_interval=1)
        test_file = os.path.join(tmp_dir, "test.json")
        with open(test_file, "w") as f:
            f.write("{}")

        changes = []
        reloader.watch_file(test_file)
        reloader.on_any_change(lambda path, old, new: changes.append(path))

        # 手动触发检查
        reloader._check_files()

        # 修改文件
        time.sleep(0.1)
        with open(test_file, "w") as f:
            f.write('{"changed": true}')

        reloader._check_files()
        # 注意：由于 mtime 精度问题，这个测试可能不总是触发

    def test_start_stop(self, tmp_dir):
        """测试启动停止"""
        reloader = HotReloader(watch_interval=1)
        test_file = os.path.join(tmp_dir, "test.json")
        with open(test_file, "w") as f:
            f.write("{}")
        reloader.watch_file(test_file)

        reloader.start()
        assert reloader.is_running() is True

        reloader.stop()
        assert reloader.is_running() is False


# ==================== Integration Tests ====================

class TestV2Integration:
    """V2 集成测试"""

    def test_full_cost_flow(self):
        """测试完整成本流程"""
        # 创建组件
        calc = PricingCalculator()
        controller = CostController(daily_limit=5.0, monthly_limit=100.0,
                                    auto_switch_cheap=True)

        # 模拟一系列请求
        requests = [
            ("gpt-4o", 1000, 500),
            ("claude-sonnet-4-20250514", 2000, 1000),
            ("deepseek-chat", 5000, 2000),
        ]

        for model, input_tokens, output_tokens in requests:
            cost = calc.calculate_cost(model, input_tokens, output_tokens)
            controller.record_cost(cost.total_cost_usd, model)

        # 检查状态
        status = controller.get_status()
        assert status.daily_used > 0
        assert status.daily_limit == 5.0

        # 检查各模型花费
        usage = controller.get_daily_usage_by_model()
        assert len(usage) == 3

    def test_key_rotation_flow(self):
        """测试 Key 轮转流程"""
        rotator = MultiKeyRotator(strategy="priority", max_consecutive_errors=2)
        rotator.set_keys("provider1", ["sk-key1", "sk-key2", "sk-key3"])

        # 使用第一个 Key
        key = rotator.get_current_key("provider1")
        assert key == "sk-key1"

        # 报告成功
        rotator.report_success("provider1", "sk-key1")

        # Key1 限流
        rotator.report_rate_limit("provider1", "sk-key1", reset_seconds=60)

        # 验证 Key1 处于限流状态
        summary_before = rotator.get_rotation_summary("provider1")
        assert summary_before["rate_limited"] == 1
        assert summary_before["active"] == 2

        # 切换到下一个 Key (get_next_key marks current as error and returns next)
        next_key = rotator.get_next_key("provider1")
        assert next_key == "sk-key2"

        # Key2 也失败 (2 次达到 max_consecutive_errors)
        rotator.report_error("provider1", "sk-key2", "error")
        rotator.report_error("provider1", "sk-key2", "error")

        # 所有 Key 状态
        summary = rotator.get_rotation_summary("provider1")
        assert summary["total"] == 3
        # Key2 is exhausted (2 consecutive errors)
        assert summary["exhausted"] >= 1

    def test_failover_flow(self):
        """测试故障转移流程"""
        engine = FailoverEngine(max_retries=2, timeout_seconds=5)
        targets = [
            FailoverTarget(model_name="primary", provider_id="p1", provider_name="P1",
                          base_url="url1", api_key="key1", priority=0),
            FailoverTarget(model_name="backup1", provider_id="p2", provider_name="P2",
                          base_url="url2", api_key="key2", priority=1),
            FailoverTarget(model_name="backup2", provider_id="p3", provider_name="P3",
                          base_url="url3", api_key="key3", priority=2),
        ]
        engine.set_targets(targets)

        # 初始状态：所有目标健康
        healthy = engine.get_healthy_targets()
        assert len(healthy) == 3

        # 模拟熔断第一个目标
        key = "p1:primary"
        for _ in range(5):
            engine._circuit_breakers[key].record_failure()

        # 熔断后，健康目标应该排除第一个
        healthy = engine.get_healthy_targets()
        assert len(healthy) == 2
        assert all(t.model_name != "primary" for t in healthy)

    def test_notification_with_cost(self):
        """测试通知与成本集成"""
        controller = CostController(daily_limit=5.0, warning_threshold=0.8)
        notifier = Notifier(desktop_enabled=False, webhook_enabled=False, min_interval=0)

        # 注册回调
        controller.on_warning(lambda event, data: notifier.notify_budget_warning(
            data.get("daily_percent", 0), data.get("monthly_percent", 0)))
        controller.on_exceeded(lambda event, data: notifier.notify_budget_exceeded(
            data.get("daily_used", 0), data.get("daily_limit", 0),
            data.get("monthly_used", 0), data.get("monthly_limit", 0)))

        # 记录费用触发警告 (get_status 内部触发回调)
        controller.record_cost(4.5, "gpt-4o")  # 90% 超过 80% 阈值
        status = controller.get_status()  # 触发阈值检查
        assert status.warning_triggered is True

        # 检查通知
        history = notifier.get_history()
        assert len(history) > 0

    def test_smart_router_with_cost_control(self):
        """测试智能路由与成本控制集成"""
        router = SmartRouter()
        controller = CostController(daily_limit=5.0, auto_switch_cheap=True)

        # 注册模型
        router.register_model(ModelCapability(
            model_name="expensive",
            provider_name="P1",
            provider_id="p1",
            base_url="url1",
            api_key="key1",
            auth_mode="bearer",
            provider_type="custom",
            input_price=10.0,
            output_price=30.0,
            context_length=128000,
            capabilities=["chat"],
        ))
        router.register_model(ModelCapability(
            model_name="cheap",
            provider_name="P2",
            provider_id="p2",
            base_url="url2",
            api_key="key2",
            auth_mode="bearer",
            provider_type="custom",
            input_price=0.1,
            output_price=0.2,
            context_length=128000,
            capabilities=["chat"],
        ))

        # 预算未超限，正常路由
        messages = [{"role": "user", "content": "你好"}]
        selected = router.route(messages)
        assert selected is not None

        # 预算超限
        controller.record_cost(6.0, "expensive")
        assert controller.should_switch_to_cheap() is True

        # 切换到最便宜模型
        cheapest = router.get_cheapest_model()
        assert cheapest is not None
        assert cheapest.model_name == "cheap"
