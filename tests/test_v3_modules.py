"""
V3 模块测试
===========
测试所有 V3 新功能模块
"""
import os
import sys
import time
import tempfile
import unittest

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAuthManager(unittest.TestCase):
    """用户认证系统测试"""

    def setUp(self):
        from app.v3_core import AuthManager
        self.temp_dir = tempfile.mkdtemp()
        self.auth = AuthManager(self.temp_dir)

    def test_create_user(self):
        """测试创建用户"""
        from app.v3_core import UserRole
        success, msg = self.auth.create_user("testuser", "password123")
        self.assertTrue(success)

    def test_create_duplicate_user(self):
        """测试重复创建用户"""
        self.auth.create_user("testuser", "password123")
        success, msg = self.auth.create_user("testuser", "password123")
        self.assertFalse(success)

    def test_authenticate_success(self):
        """测试认证成功"""
        self.auth.create_user("testuser", "password123")
        token = self.auth.authenticate("testuser", "password123")
        self.assertIsNotNone(token)

    def test_authenticate_wrong_password(self):
        """测试密码错误"""
        self.auth.create_user("testuser", "password123")
        token = self.auth.authenticate("testuser", "wrongpass")
        self.assertIsNone(token)

    def test_authenticate_nonexistent_user(self):
        """测试不存在的用户"""
        token = self.auth.authenticate("nouser", "password123")
        self.assertIsNone(token)

    def test_verify_token(self):
        """测试验证 token"""
        self.auth.create_user("testuser", "password123")
        token = self.auth.authenticate("testuser", "password123")
        user = self.auth.verify_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")

    def test_verify_invalid_token(self):
        """测试无效 token"""
        user = self.auth.verify_token("invalid_token")
        self.assertIsNone(user)

    def test_logout(self):
        """测试登出"""
        self.auth.create_user("testuser", "password123")
        token = self.auth.authenticate("testuser", "password123")
        self.auth.logout(token)
        user = self.auth.verify_token(token)
        self.assertIsNone(user)

    def test_delete_user(self):
        """测试删除用户"""
        self.auth.create_user("testuser", "password123")
        result = self.auth.delete_user("testuser")
        self.assertTrue(result)

    def test_delete_nonexistent_user(self):
        """测试删除不存在的用户"""
        result = self.auth.delete_user("nouser")
        self.assertFalse(result)

    def test_has_permission_admin(self):
        """测试管理员权限"""
        from app.v3_core import UserRole
        self.auth.create_user("admin2", "pass", UserRole.ADMIN)
        user = self.auth.get_user("admin2")
        self.assertTrue(self.auth.has_permission(user, "manage_users"))
        self.assertTrue(self.auth.has_permission(user, "call_models"))

    def test_has_permission_viewer(self):
        """测试查看者权限"""
        from app.v3_core import UserRole
        self.auth.create_user("viewer", "pass", UserRole.VIEWER)
        user = self.auth.get_user("viewer")
        self.assertTrue(self.auth.has_permission(user, "view_stats"))
        self.assertFalse(self.auth.has_permission(user, "call_models"))

    def test_get_all_users(self):
        """测试获取所有用户"""
        self.auth.create_user("user1", "pass")
        self.auth.create_user("user2", "pass")
        users = self.auth.get_all_users()
        # admin + user1 + user2
        self.assertGreaterEqual(len(users), 3)

    def test_default_admin_exists(self):
        """测试默认管理员存在"""
        admin = self.auth.get_user("admin")
        self.assertIsNotNone(admin)

    def test_password_hashing(self):
        """测试密码哈希"""
        hash1 = self.auth._hash_password("testpass")
        hash2 = self.auth._hash_password("testpass")
        # 不同盐值，哈希应该不同
        self.assertNotEqual(hash1, hash2)
        # 但都能验证通过
        self.assertTrue(self.auth._verify_password("testpass", hash1))
        self.assertTrue(self.auth._verify_password("testpass", hash2))


class TestRequestCache(unittest.TestCase):
    """请求缓存测试"""

    def setUp(self):
        from app.v3_core import RequestCache
        self.cache = RequestCache(max_size=100, default_ttl=60)

    def test_cache_miss(self):
        """测试缓存未命中"""
        result = self.cache.get("gpt-4o", [{"role": "user", "content": "hello"}])
        self.assertIsNone(result)

    def test_cache_hit(self):
        """测试缓存命中"""
        messages = [{"role": "user", "content": "hello"}]
        response = {"content": "hi there"}
        self.cache.set("gpt-4o", messages, response)
        result = self.cache.get("gpt-4o", messages)
        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "hi there")

    def test_cache_different_messages(self):
        """测试不同消息不命中"""
        self.cache.set("gpt-4o", [{"role": "user", "content": "a"}], {"content": "resp1"})
        result = self.cache.get("gpt-4o", [{"role": "user", "content": "b"}])
        self.assertIsNone(result)

    def test_cache_expiry(self):
        """测试缓存过期"""
        messages = [{"role": "user", "content": "hello"}]
        self.cache.set("gpt-4o", messages, {"content": "hi"}, ttl=1)
        time.sleep(1.1)
        result = self.cache.get("gpt-4o", messages)
        self.assertIsNone(result)

    def test_cache_clear(self):
        """测试清空缓存"""
        self.cache.set("gpt-4o", [{"role": "user", "content": "a"}], {"content": "resp"})
        self.cache.clear()
        result = self.cache.get("gpt-4o", [{"role": "user", "content": "a"}])
        self.assertIsNone(result)

    def test_cache_stats(self):
        """测试缓存统计"""
        self.cache.set("gpt-4o", [{"role": "user", "content": "a"}], {"content": "resp"})
        self.cache.get("gpt-4o", [{"role": "user", "content": "a"}])  # hit
        self.cache.get("gpt-4o", [{"role": "user", "content": "b"}])  # miss
        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hit_rate"], 50.0)

    def test_cache_max_size(self):
        """测试缓存最大容量"""
        from app.v3_core import RequestCache
        cache = RequestCache(max_size=5, default_ttl=60)
        for i in range(10):
            cache.set("model", [{"role": "user", "content": f"msg{i}"}], {"content": f"resp{i}"})
        stats = cache.get_stats()
        self.assertLessEqual(stats["size"], 5)

    def test_cache_different_models(self):
        """测试不同模型独立缓存"""
        msg = [{"role": "user", "content": "hello"}]
        self.cache.set("gpt-4o", msg, {"content": "gpt response"})
        self.cache.set("claude-sonnet-4", msg, {"content": "claude response"})
        r1 = self.cache.get("gpt-4o", msg)
        r2 = self.cache.get("claude-sonnet-4", msg)
        self.assertEqual(r1["content"], "gpt response")
        self.assertEqual(r2["content"], "claude response")


class TestPromptManager(unittest.TestCase):
    """Prompt 管理测试"""

    def setUp(self):
        from app.v3_core import PromptManager
        self.temp_dir = tempfile.mkdtemp()
        self.pm = PromptManager(self.temp_dir)

    def test_default_prompts_exist(self):
        """测试默认 Prompt 存在"""
        prompts = self.pm.get_all()
        self.assertGreaterEqual(len(prompts), 4)

    def test_create_prompt(self):
        """测试创建 Prompt"""
        prompt = self.pm.create(
            name="测试模板",
            description="测试描述",
            content="你好 {{name}}",
            category="测试",
            variables=["name"],
            tags=["测试"],
        )
        self.assertIsNotNone(prompt.id)
        self.assertEqual(prompt.name, "测试模板")

    def test_get_prompt(self):
        """测试获取 Prompt"""
        created = self.pm.create(name="测试", content="内容")
        fetched = self.pm.get(created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "测试")

    def test_update_prompt(self):
        """测试更新 Prompt"""
        created = self.pm.create(name="旧名称", content="内容")
        updated = self.pm.update(created.id, name="新名称")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.name, "新名称")

    def test_delete_prompt(self):
        """测试删除 Prompt"""
        created = self.pm.create(name="待删除", content="内容")
        result = self.pm.delete(created.id)
        self.assertTrue(result)
        self.assertIsNone(self.pm.get(created.id))

    def test_search_prompts(self):
        """测试搜索 Prompt"""
        results = self.pm.search("代码")
        self.assertGreater(len(results), 0)

    def test_get_by_category(self):
        """测试按分类获取"""
        coding = self.pm.get_by_category("编程")
        self.assertGreater(len(coding), 0)

    def test_render_prompt(self):
        """测试渲染 Prompt"""
        created = self.pm.create(
            name="问候",
            content="你好 {{name}}，我是 {{role}}",
            variables=["name", "role"],
        )
        rendered = self.pm.use_prompt(created.id, name="小明", role="助手")
        self.assertEqual(rendered, "你好 小明，我是 助手")

    def test_get_categories(self):
        """测试获取分类列表"""
        categories = self.pm.get_categories()
        self.assertIn("编程", categories)

    def test_use_count_increment(self):
        """测试使用计数"""
        created = self.pm.create(name="计数测试", content="内容")
        self.pm.use_prompt(created.id)
        self.pm.use_prompt(created.id)
        prompt = self.pm.get(created.id)
        self.assertEqual(prompt.use_count, 2)


class TestAnalyticsEngine(unittest.TestCase):
    """数据分析引擎测试"""

    def setUp(self):
        from app.v3_analytics import AnalyticsEngine, UsageRecord
        self.temp_dir = tempfile.mkdtemp()
        self.analytics = AnalyticsEngine(self.temp_dir)

    def test_record_usage(self):
        """测试记录使用"""
        from app.v3_analytics import UsageRecord
        record = UsageRecord(
            timestamp=int(time.time()),
            model="gpt-4o",
            provider="openai",
            user="testuser",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.001,
            cost_cny=0.0072,
            response_time_ms=1500,
            status="success",
        )
        self.analytics.record(record)
        overview = self.analytics.get_overview(1)
        self.assertEqual(overview["total_requests"], 1)

    def test_overview_stats(self):
        """测试概览统计"""
        from app.v3_analytics import UsageRecord
        for i in range(5):
            self.analytics.record(UsageRecord(
                timestamp=int(time.time()),
                model="gpt-4o",
                provider="openai",
                user="user1",
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                cost_usd=0.001,
                cost_cny=0.0072,
                response_time_ms=1000,
                status="success",
            ))
        overview = self.analytics.get_overview(1)
        self.assertEqual(overview["total_requests"], 5)
        self.assertEqual(overview["total_tokens"], 1500)

    def test_daily_usage(self):
        """测试每日使用量"""
        from app.v3_analytics import UsageRecord
        self.analytics.record(UsageRecord(
            timestamp=int(time.time()),
            model="gpt-4o",
            provider="openai",
            user="user1",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.001,
            cost_cny=0.0072,
            response_time_ms=1000,
            status="success",
        ))
        daily = self.analytics.get_daily_usage(1)
        self.assertGreater(len(daily), 0)

    def test_model_distribution(self):
        """测试模型分布"""
        from app.v3_analytics import UsageRecord
        for model in ["gpt-4o", "gpt-4o", "claude-sonnet-4"]:
            self.analytics.record(UsageRecord(
                timestamp=int(time.time()),
                model=model,
                provider="test",
                user="user1",
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                cost_usd=0.001,
                cost_cny=0.0072,
                response_time_ms=1000,
                status="success",
            ))
        dist = self.analytics.get_model_distribution(1)
        self.assertEqual(len(dist), 2)

    def test_user_ranking(self):
        """测试用户排行"""
        from app.v3_analytics import UsageRecord
        for i in range(3):
            self.analytics.record(UsageRecord(
                timestamp=int(time.time()),
                model="gpt-4o",
                provider="openai",
                user="heavy_user",
                prompt_tokens=1000,
                completion_tokens=2000,
                total_tokens=3000,
                cost_usd=0.01,
                cost_cny=0.072,
                response_time_ms=1000,
                status="success",
            ))
        for i in range(1):
            self.analytics.record(UsageRecord(
                timestamp=int(time.time()),
                model="gpt-4o",
                provider="openai",
                user="light_user",
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                cost_usd=0.001,
                cost_cny=0.0072,
                response_time_ms=1000,
                status="success",
            ))
        ranking = self.analytics.get_user_ranking(1)
        self.assertEqual(ranking[0]["user"], "heavy_user")

    def test_performance_stats(self):
        """测试性能统计"""
        from app.v3_analytics import UsageRecord
        for i in range(10):
            self.analytics.record(UsageRecord(
                timestamp=int(time.time()),
                model="gpt-4o",
                provider="openai",
                user="user1",
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                cost_usd=0.001,
                cost_cny=0.0072,
                response_time_ms=1000 + i * 100,
                status="success" if i < 9 else "error",
            ))
        perf = self.analytics.get_performance_stats(1)
        self.assertIn("avg_latency", perf)
        self.assertIn("p50", perf)
        self.assertIn("p90", perf)

    def test_cost_trend(self):
        """测试成本趋势"""
        from app.v3_analytics import UsageRecord
        self.analytics.record(UsageRecord(
            timestamp=int(time.time()),
            model="gpt-4o",
            provider="openai",
            user="user1",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.005,
            cost_cny=0.036,
            response_time_ms=1000,
            status="success",
        ))
        trend = self.analytics.get_cost_trend(1)
        self.assertGreater(len(trend), 0)
        self.assertIn("cost_usd", trend[0])

    def test_export_json(self):
        """测试导出 JSON"""
        from app.v3_analytics import UsageRecord
        self.analytics.record(UsageRecord(
            timestamp=int(time.time()),
            model="gpt-4o",
            provider="openai",
            user="user1",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.001,
            cost_cny=0.0072,
            response_time_ms=1000,
            status="success",
        ))
        output = os.path.join(self.temp_dir, "report.json")
        self.analytics.export_json(output, 1)
        self.assertTrue(os.path.exists(output))

    def test_get_stats(self):
        """测试统计摘要"""
        stats = self.analytics.get_stats()
        self.assertIn("total_records", stats)
        self.assertIn("db_size_mb", stats)


class TestSmartScheduler(unittest.TestCase):
    """智能调度器测试"""

    def setUp(self):
        from app.v3_scheduler import SmartScheduler
        self.scheduler = SmartScheduler()

    def test_schedule_returns_decision(self):
        """测试调度返回决策"""
        decision = self.scheduler.schedule(task_type="chat")
        self.assertIsNotNone(decision.model)
        self.assertIsNotNone(decision.reason)

    def test_schedule_coding_task(self):
        """测试编程任务调度"""
        decision = self.scheduler.schedule(task_type="code", require_coding=True)
        self.assertIsNotNone(decision.model)

    def test_schedule_cheap_task(self):
        """测试低成本任务调度"""
        decision = self.scheduler.schedule(task_type="cheap")
        self.assertIsNotNone(decision.model)

    def test_schedule_complex_task(self):
        """测试复杂任务调度"""
        decision = self.scheduler.schedule(task_type="complex")
        self.assertIsNotNone(decision.model)

    def test_set_strategy(self):
        """测试设置策略"""
        self.scheduler.set_strategy("speed")
        self.assertEqual(self.scheduler.get_strategy(), "speed")

    def test_set_invalid_strategy(self):
        """测试设置无效策略"""
        self.scheduler.set_strategy("invalid")
        # 应保持原策略
        self.assertNotEqual(self.scheduler.get_strategy(), "invalid")

    def test_record_result(self):
        """测试记录结果"""
        self.scheduler.record_result("gpt-4o", 1500, True, 0.001)
        metrics = self.scheduler.get_metrics()
        self.assertGreater(len(metrics), 0)

    def test_schedule_with_preferred_models(self):
        """测试指定候选模型"""
        decision = self.scheduler.schedule(
            task_type="chat",
            preferred_models=["gpt-4o", "claude-sonnet-4"],
        )
        self.assertIn(decision.model, ["gpt-4o", "claude-sonnet-4"])

    def test_get_recommendations(self):
        """测试获取推荐"""
        recs = self.scheduler.get_recommendations()
        self.assertGreater(len(recs), 0)
        self.assertIn("scenario", recs[0])
        self.assertIn("recommended_model", recs[0])

    def test_get_stats(self):
        """测试统计"""
        stats = self.scheduler.get_stats()
        self.assertIn("strategy", stats)
        self.assertIn("tracked_models", stats)

    def test_strategy_affects_decision(self):
        """测试策略影响决策"""
        self.scheduler.set_strategy("cost")
        cheap_decision = self.scheduler.schedule(task_type="cheap")
        self.assertIsNotNone(cheap_decision.model)


class TestMCPServer(unittest.TestCase):
    """MCP 服务器测试"""

    def setUp(self):
        from app.v3_mcp import MCPServer
        self.temp_dir = tempfile.mkdtemp()
        self.mcp = MCPServer(self.temp_dir)

    def test_default_tools_registered(self):
        """测试默认工具已注册"""
        tools = self.mcp.get_tools()
        self.assertGreaterEqual(len(tools), 5)

    def test_get_tool(self):
        """测试获取工具"""
        tool = self.mcp.get_tool("read_file")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "read_file")

    def test_get_nonexistent_tool(self):
        """测试获取不存在的工具"""
        tool = self.mcp.get_tool("nonexistent")
        self.assertIsNone(tool)

    def test_call_tool_not_found(self):
        """测试调用不存在的工具"""
        result = self.mcp.call_tool("nonexistent", {})
        self.assertIn("error", result)

    def test_call_read_file(self):
        """测试调用读取文件工具"""
        # 创建一个测试文件
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello world")
        result = self.mcp.call_tool("read_file", {"path": test_file})
        self.assertTrue(result["success"])
        self.assertEqual(result["result"]["content"], "hello world")

    def test_call_read_file_not_found(self):
        """测试读取不存在的文件"""
        result = self.mcp.call_tool("read_file", {"path": "/nonexistent/file.txt"})
        self.assertFalse(result["success"])

    def test_call_write_file(self):
        """测试调用写入文件工具"""
        test_file = os.path.join(self.temp_dir, "output.txt")
        result = self.mcp.call_tool("write_file", {
            "path": test_file,
            "content": "test content",
        })
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(test_file))

    def test_call_list_files(self):
        """测试调用列出文件工具"""
        # 创建一些文件
        for i in range(3):
            with open(os.path.join(self.temp_dir, f"file{i}.txt"), "w") as f:
                f.write("content")
        result = self.mcp.call_tool("list_files", {"path": self.temp_dir})
        self.assertTrue(result["success"])
        self.assertGreater(result["result"]["count"], 0)

    def test_call_run_command(self):
        """默认发行版禁用高风险 Shell 工具"""
        result = self.mcp.call_tool("run_command", {"command": "echo hello"})
        self.assertIn("error", result)

    def test_call_run_command_explicitly_enabled(self):
        """显式启用后仍可使用 Shell 工具"""
        from app.v3_mcp import MCPServer
        mcp = MCPServer(self.temp_dir, enable_shell=True)
        result = mcp.call_tool("run_command", {"command": "echo hello"})
        self.assertTrue(result["success"])
        self.assertIn("hello", result["result"]["stdout"])

    def test_get_tools_schema(self):
        """测试获取工具 Schema"""
        schemas = self.mcp.get_tools_schema()
        self.assertGreater(len(schemas), 0)
        self.assertIn("type", schemas[0])
        self.assertIn("function", schemas[0])

    def test_register_custom_tool(self):
        """测试注册自定义工具"""
        from app.v3_mcp import MCPTool, MCPToolType

        def my_handler(args):
            return {"message": "custom tool"}

        tool = MCPTool(
            name="my_tool",
            description="自定义工具",
            parameters={"type": "object", "properties": {}},
            tool_type=MCPToolType.CUSTOM,
            handler=my_handler,
        )
        self.mcp.register_tool(tool)
        result = self.mcp.call_tool("my_tool", {})
        self.assertTrue(result["success"])

    def test_unregister_tool(self):
        """测试注销工具"""
        from app.v3_mcp import MCPTool, MCPToolType
        tool = MCPTool(
            name="temp_tool",
            description="临时工具",
            parameters={"type": "object", "properties": {}},
            tool_type=MCPToolType.CUSTOM,
        )
        self.mcp.register_tool(tool)
        self.mcp.unregister_tool("temp_tool")
        self.assertIsNone(self.mcp.get_tool("temp_tool"))


class TestPluginManager(unittest.TestCase):
    """插件管理器测试"""

    def setUp(self):
        from app.v3_plugins import PluginManager
        self.temp_dir = tempfile.mkdtemp()
        # 在临时目录中创建 plugins 子目录
        plugins_dir = os.path.join(self.temp_dir, "plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        self.pm = PluginManager(plugins_dir)

    def test_builtin_plugins_exist(self):
        """测试内置插件存在"""
        plugins = self.pm.get_all_plugins()
        self.assertGreaterEqual(len(plugins), 5)

    def test_get_plugin(self):
        """测试获取插件"""
        plugin = self.pm.get_plugin("slack_notifier")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "Slack 通知")

    def test_enable_plugin(self):
        """测试启用插件"""
        success = self.pm.enable_plugin("slack_notifier")
        self.assertTrue(success)
        plugin = self.pm.get_plugin("slack_notifier")
        from app.v3_plugins import PluginState
        self.assertEqual(plugin.state, PluginState.ENABLED)

    def test_disable_plugin(self):
        """测试禁用插件"""
        self.pm.enable_plugin("slack_notifier")
        success = self.pm.disable_plugin("slack_notifier")
        self.assertTrue(success)
        plugin = self.pm.get_plugin("slack_notifier")
        from app.v3_plugins import PluginState
        self.assertEqual(plugin.state, PluginState.DISABLED)

    def test_get_plugins_by_type(self):
        """测试按类型获取"""
        from app.v3_plugins import PluginType
        notifiers = self.pm.get_plugins_by_type(PluginType.NOTIFICATION)
        self.assertGreaterEqual(len(notifiers), 3)

    def test_get_enabled_plugins(self):
        """测试获取已启用插件"""
        self.pm.enable_plugin("slack_notifier")
        enabled = self.pm.get_enabled_plugins()
        self.assertGreaterEqual(len(enabled), 1)

    def test_scan_plugins(self):
        """测试扫描插件"""
        # 创建一个新的插件文件
        plugin_file = os.path.join(self.temp_dir, "plugins", "test_plugin.py")
        with open(plugin_file, "w") as f:
            f.write("# Test plugin\n")
        new_plugins = self.pm.scan_plugins()
        self.assertIn("test_plugin", new_plugins)

    def test_get_stats(self):
        """测试统计"""
        stats = self.pm.get_stats()
        self.assertIn("total", stats)
        self.assertIn("states", stats)

    def test_execute_hooks(self):
        """测试执行钩子"""
        result = self.pm.execute_hooks("on_notification", {"message": "test"})
        self.assertIn("message", result)


class TestAuditLogger(unittest.TestCase):
    """审计日志测试"""

    def setUp(self):
        from app.v3_core import AuditLogger
        self.temp_dir = tempfile.mkdtemp()
        self.audit = AuditLogger(self.temp_dir)

    def test_log_action(self):
        """测试记录日志"""
        self.audit.log("test_action", user="testuser", details={"key": "value"})
        logs = self.audit.get_logs()
        self.assertGreater(len(logs), 0)

    def test_get_logs_with_limit(self):
        """测试获取日志带限制"""
        for i in range(10):
            self.audit.log(f"action_{i}")
        logs = self.audit.get_logs(limit=5)
        self.assertEqual(len(logs), 5)

    def test_get_logs_filter_by_action(self):
        """测试按动作过滤"""
        self.audit.log("login", user="user1")
        self.audit.log("logout", user="user1")
        self.audit.log("login", user="user2")
        logs = self.audit.get_logs(action="login")
        self.assertEqual(len(logs), 2)

    def test_get_logs_filter_by_user(self):
        """测试按用户过滤"""
        self.audit.log("action1", user="alice")
        self.audit.log("action2", user="bob")
        self.audit.log("action3", user="alice")
        logs = self.audit.get_logs(user="alice")
        self.assertEqual(len(logs), 2)

    def test_get_stats(self):
        """测试统计"""
        self.audit.log("login")
        self.audit.log("login")
        self.audit.log("logout")
        stats = self.audit.get_stats()
        self.assertEqual(stats["total_logs"], 3)
        self.assertEqual(stats["actions"]["login"], 2)


class TestV3Integration(unittest.TestCase):
    """V3 集成测试"""

    def test_full_flow(self):
        """测试完整流程"""
        from app.v3_core import AuthManager, RequestCache, PromptManager
        from app.v3_analytics import AnalyticsEngine, UsageRecord
        from app.v3_scheduler import SmartScheduler

        temp_dir = tempfile.mkdtemp()

        # 1. 创建用户
        auth = AuthManager(temp_dir)
        auth.create_user("testuser", "pass123")
        token = auth.authenticate("testuser", "pass123")
        self.assertIsNotNone(token)

        # 2. 创建 Prompt
        pm = PromptManager(temp_dir)
        prompt = pm.create(name="测试", content="你好 {{name}}")
        rendered = pm.use_prompt(prompt.id, name="世界")
        self.assertEqual(rendered, "你好 世界")

        # 3. 使用缓存
        cache = RequestCache()
        cache.set("gpt-4o", [{"role": "user", "content": "hi"}], {"content": "hello"})
        cached = cache.get("gpt-4o", [{"role": "user", "content": "hi"}])
        self.assertIsNotNone(cached)

        # 4. 记录分析
        analytics = AnalyticsEngine(temp_dir)
        analytics.record(UsageRecord(
            timestamp=int(time.time()),
            model="gpt-4o",
            provider="openai",
            user="testuser",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.001,
            cost_cny=0.0072,
            response_time_ms=1000,
            status="success",
        ))
        overview = analytics.get_overview(1)
        self.assertEqual(overview["total_requests"], 1)

        # 5. 调度
        scheduler = SmartScheduler()
        decision = scheduler.schedule(task_type="chat")
        self.assertIsNotNone(decision.model)

    def test_auth_with_mcp(self):
        """测试认证 + MCP"""
        from app.v3_core import AuthManager
        from app.v3_mcp import MCPServer

        temp_dir = tempfile.mkdtemp()
        auth = AuthManager(temp_dir)
        mcp = MCPServer(temp_dir, enable_shell=True)

        # 创建用户并认证
        auth.create_user("developer", "devpass")
        token = auth.authenticate("developer", "devpass")
        user = auth.verify_token(token)

        # 检查权限
        if auth.has_permission(user, "call_models"):
            result = mcp.call_tool("run_command", {"command": "echo test"})
            self.assertTrue(result["success"])

    def test_scheduler_with_analytics(self):
        """测试调度器 + 分析"""
        from app.v3_scheduler import SmartScheduler
        from app.v3_analytics import AnalyticsEngine, UsageRecord

        temp_dir = tempfile.mkdtemp()
        scheduler = SmartScheduler()
        analytics = AnalyticsEngine(temp_dir)

        # 模拟请求
        for i in range(5):
            decision = scheduler.schedule(task_type="chat")
            scheduler.record_result(
                decision.model,
                latency_ms=1000 + i * 200,
                success=True,
                cost=0.001,
            )
            analytics.record(UsageRecord(
                timestamp=int(time.time()),
                model=decision.model,
                provider=decision.provider,
                user="test",
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                cost_usd=0.001,
                cost_cny=0.0072,
                response_time_ms=1000 + i * 200,
                status="success",
            ))

        # 验证数据
        metrics = scheduler.get_metrics()
        self.assertGreater(len(metrics), 0)

        overview = analytics.get_overview(1)
        self.assertEqual(overview["total_requests"], 5)


if __name__ == "__main__":
    unittest.main()
