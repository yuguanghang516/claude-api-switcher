"""
V3 统一网关服务器
=================
整合 V1/V2/V3 功能的统一入口

启动方式:
    python -m app.v3_gateway
    或
    python app/v3_gateway.py
"""
import os
import sys
import time
import json
import signal
import logging
import threading
from typing import Optional

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(DATA_DIR, "v3_gateway.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("v3_gateway")


class V3Gateway:
    """V3 统一网关"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.data_dir = self.config.get("data_dir", DATA_DIR)
        self.port = self.config.get("port", 8080)
        # 桌面工具默认只允许本机访问；公开监听必须由用户显式配置。
        self.host = self.config.get("host", "127.0.0.1")

        # 模块实例
        self.auth_manager = None
        self.prompt_manager = None
        self.analytics = None
        self.scheduler = None
        self.mcp_server = None
        self.plugin_manager = None
        self.cache = None
        self.audit_logger = None
        self.web_app = None

        # 运行状态
        self._running = False
        self._lock = threading.RLock()

    def init_modules(self):
        """初始化所有模块"""
        logger.info("正在初始化 V3 模块...")

        # 1. 审计日志
        from app.v3_core import AuditLogger
        self.audit_logger = AuditLogger(self.data_dir, logger)
        logger.info("✅ 审计日志模块已初始化")

        # 2. 用户认证
        from app.v3_core import AuthManager
        self.auth_manager = AuthManager(self.data_dir, logger)
        logger.info("✅ 用户认证模块已初始化")

        # 3. 请求缓存
        from app.v3_core import RequestCache
        self.cache = RequestCache(
            max_size=self.config.get("cache_size", 1000),
            default_ttl=self.config.get("cache_ttl", 300),
            logger=logger,
        )
        logger.info("✅ 请求缓存模块已初始化")

        # 4. Prompt 管理
        from app.v3_core import PromptManager
        self.prompt_manager = PromptManager(self.data_dir, logger)
        logger.info("✅ Prompt 管理模块已初始化")

        # 5. 数据分析
        from app.v3_analytics import AnalyticsEngine
        self.analytics = AnalyticsEngine(self.data_dir, logger)
        logger.info("✅ 数据分析模块已初始化")

        # 6. 智能调度
        from app.v3_scheduler import SmartScheduler
        # 尝试导入价格计算器
        pricing_calculator = None
        try:
            from app.pricing import PricingCalculator
            pricing_calculator = PricingCalculator()
        except ImportError:
            pass
        self.scheduler = SmartScheduler(pricing_calculator, logger)
        logger.info("✅ 智能调度模块已初始化")

        # 7. MCP 支持
        from app.v3_mcp import MCPServer
        self.mcp_server = MCPServer(
            self.data_dir, logger,
            enable_shell=bool(self.config.get("enable_shell_tools", False)))
        logger.info("✅ MCP 支持模块已初始化")

        # 8. 插件系统
        from app.v3_plugins import PluginManager
        plugins_dir = os.path.join(BASE_DIR, "plugins")
        self.plugin_manager = PluginManager(plugins_dir, logger)
        logger.info("✅ 插件系统已初始化")

        # 审计记录
        if self.audit_logger:
            self.audit_logger.log("system_start", user="system")

        logger.info("所有 V3 模块初始化完成")

    def start_web_server(self):
        """启动 Web 服务器"""
        try:
            from app.v3_web import create_web_app
            self.web_app = create_web_app(
                data_dir=self.data_dir,
                auth_manager=self.auth_manager,
                prompt_manager=self.prompt_manager,
                analytics=self.analytics,
                scheduler=self.scheduler,
                mcp_server=self.mcp_server,
                plugin_manager=self.plugin_manager,
                cache=self.cache,
                logger=logger,
            )

            if self.web_app is None:
                logger.warning("FastAPI 不可用，Web 控制面板未启动")
                return

            # 使用 uvicorn 启动
            import uvicorn

            config = uvicorn.Config(
                app=self.web_app,
                host=self.host,
                port=self.port,
                log_level="info",
                access_log=True,
            )
            self._server = uvicorn.Server(config)

            # 在后台线程运行
            self._server_thread = threading.Thread(
                target=self._server.run,
                daemon=True,
                name="uvicorn",
            )
            self._server_thread.start()
            logger.info(f"🌐 Web 控制面板已启动: http://{self.host}:{self.port}")

        except ImportError as e:
            logger.warning(f"Web 服务器依赖缺失: {e}")
            logger.warning("请运行: pip install fastapi uvicorn")
        except Exception as e:
            logger.error(f"Web 服务器启动失败: {e}")

    def start(self):
        """启动网关"""
        logger.info("=" * 60)
        logger.info("🚀 AI Router V3 正在启动...")
        logger.info("=" * 60)

        with self._lock:
            self._running = True

        # 初始化模块
        self.init_modules()

        # 启动 Web 服务器
        self.start_web_server()

        # 启动后台任务
        self._start_background_tasks()

        logger.info("=" * 60)
        logger.info("✅ AI Router V3 启动完成!")
        logger.info(f"   📊 Web 控制面板: http://localhost:{self.port}")
        logger.info(f"   🔧 API 端点: http://localhost:{self.port}/api")
        if self.auth_manager and self.auth_manager.bootstrap_admin_password:
            logger.warning("首次管理员凭据已写入数据目录中的 v3_bootstrap_admin.txt；首次登录后请修改密码并删除该文件。")
        logger.info("=" * 60)

        if self.audit_logger:
            self.audit_logger.log("gateway_started", user="system",
                                details={"port": self.port})

    def stop(self):
        """停止网关"""
        logger.info("正在停止 AI Router V3...")
        with self._lock:
            self._running = False

        if self.audit_logger:
            self.audit_logger.log("gateway_stopped", user="system")

        logger.info("AI Router V3 已停止")

    def _start_background_tasks(self):
        """启动后台任务"""
        # 缓存清理
        def cleanup_cache():
            while self._running:
                time.sleep(60)
                if self.cache:
                    self.cache.cleanup_expired()

        self._cleanup_thread = threading.Thread(
            target=cleanup_cache,
            daemon=True,
            name="cache-cleanup",
        )
        self._cleanup_thread.start()

    def is_running(self) -> bool:
        """检查是否运行中"""
        return self._running

    def get_status(self) -> dict:
        """获取网关状态"""
        return {
            "running": self._running,
            "version": "3.0.0",
            "modules": {
                "auth": self.auth_manager is not None,
                "cache": self.cache is not None,
                "prompts": self.prompt_manager is not None,
                "analytics": self.analytics is not None,
                "scheduler": self.scheduler is not None,
                "mcp": self.mcp_server is not None,
                "plugins": self.plugin_manager is not None,
            },
            "port": self.port,
            "uptime": time.time(),
        }


# ==================== 主入口 ====================

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="AI Router V3 网关服务器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--data-dir", default=DATA_DIR, help="数据目录")
    parser.add_argument("--cache-size", type=int, default=1000, help="缓存大小")
    parser.add_argument("--cache-ttl", type=int, default=300, help="缓存 TTL (秒)")
    parser.add_argument("--debug", action="store_true", help="调试模式")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    config = {
        "host": args.host,
        "port": args.port,
        "data_dir": args.data_dir,
        "cache_size": args.cache_size,
        "cache_ttl": args.cache_ttl,
    }

    gateway = V3Gateway(config)

    # 信号处理
    def signal_handler(sig, frame):
        gateway.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动
    gateway.start()

    # 保持运行
    try:
        while gateway.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        gateway.stop()


if __name__ == "__main__":
    main()
