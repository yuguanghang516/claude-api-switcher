"""
V3 插件系统
===========
可扩展的插件架构，支持动态加载、卸载、配置

插件类型：
- 模型提供者插件 (Provider Plugin)
- 中间件插件 (Middleware Plugin)
- 通知插件 (Notification Plugin)
- 分析插件 (Analytics Plugin)
"""
import os
import json
import importlib
import importlib.util
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class PluginType(Enum):
    """插件类型"""
    PROVIDER = "provider"       # 模型提供者
    MIDDLEWARE = "middleware"   # 请求/响应中间件
    NOTIFICATION = "notification"  # 通知方式
    ANALYTICS = "analytics"     # 数据分析
    CUSTOM = "custom"           # 自定义


class PluginState(Enum):
    """插件状态"""
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginInfo:
    """插件信息"""
    id: str
    name: str
    version: str
    description: str
    author: str
    plugin_type: PluginType
    state: PluginState = PluginState.UNLOADED
    config: Dict = field(default_factory=dict)
    hooks: List[str] = field(default_factory=list)
    loaded_at: int = 0
    error: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "type": self.plugin_type.value,
            "state": self.state.value,
            "config": self.config,
            "hooks": self.hooks,
            "loaded_at": self.loaded_at,
            "error": self.error,
        }


class PluginInterface:
    """插件接口 - 所有插件必须实现"""

    def __init__(self):
        self.plugin_info: Optional[PluginInfo] = None

    def on_load(self, config: Dict) -> bool:
        """加载插件"""
        return True

    def on_unload(self):
        """卸载插件"""
        pass

    def on_enable(self):
        """启用插件"""
        pass

    def on_disable(self):
        """禁用插件"""
        pass

    def get_hooks(self) -> Dict[str, Callable]:
        """返回钩子函数"""
        return {}


class PluginManager:
    """插件管理器"""

    def __init__(self, plugins_dir: str = "plugins", logger=None):
        self.plugins_dir = plugins_dir
        self.logger = logger
        self._plugins: Dict[str, PluginInterface] = {}
        self._info: Dict[str, PluginInfo] = {}
        self._lock = threading.RLock()
        self._hooks: Dict[str, List[tuple]] = {}  # hook_name -> [(plugin_id, func)]

        # 确保插件目录存在
        os.makedirs(plugins_dir, exist_ok=True)

        # 注册内置插件
        self._register_builtin_plugins()

    def _register_builtin_plugins(self):
        """注册内置插件"""
        # Slack 通知插件
        self._info["slack_notifier"] = PluginInfo(
            id="slack_notifier",
            name="Slack 通知",
            version="1.0.0",
            description="通过 Slack Webhook 发送通知",
            author="AI Router",
            plugin_type=PluginType.NOTIFICATION,
            hooks=["on_notification"],
        )

        # Discord 通知插件
        self._info["discord_notifier"] = PluginInfo(
            id="discord_notifier",
            name="Discord 通知",
            version="1.0.0",
            description="通过 Discord Webhook 发送通知",
            author="AI Router",
            plugin_type=PluginType.NOTIFICATION,
            hooks=["on_notification"],
        )

        # 企业微信通知插件
        self._info["wecom_notifier"] = PluginInfo(
            id="wecom_notifier",
            name="企业微信通知",
            version="1.0.0",
            description="通过企业微信 Webhook 发送通知",
            author="AI Router",
            plugin_type=PluginType.NOTIFICATION,
            hooks=["on_notification"],
        )

        # 请求日志中间件
        self._info["request_logger"] = PluginInfo(
            id="request_logger",
            name="请求日志",
            version="1.0.0",
            description="记录所有 API 请求和响应",
            author="AI Router",
            plugin_type=PluginType.MIDDLEWARE,
            hooks=["pre_request", "post_response"],
        )

        # 速率限制中间件
        self._info["rate_limiter"] = PluginInfo(
            id="rate_limiter",
            name="速率限制",
            version="1.0.0",
            description="限制 API 请求频率",
            author="AI Router",
            plugin_type=PluginType.MIDDLEWARE,
            hooks=["pre_request"],
        )

        # 用量统计插件
        self._info["usage_analytics"] = PluginInfo(
            id="usage_analytics",
            name="用量统计",
            version="1.0.0",
            description="统计 API 使用量和成本",
            author="AI Router",
            plugin_type=PluginType.ANALYTICS,
            hooks=["post_response"],
        )

    def load_plugin(self, plugin_id: str, config: Dict = None) -> tuple:
        """加载插件"""
        with self._lock:
            info = self._info.get(plugin_id)
            if not info:
                return False, f"插件不存在: {plugin_id}"

            if info.state in (PluginState.LOADED, PluginState.ENABLED):
                return False, f"插件已加载: {plugin_id}"

            try:
                # 从文件加载
                plugin_file = os.path.join(self.plugins_dir, f"{plugin_id}.py")
                if os.path.exists(plugin_file):
                    spec = importlib.util.spec_from_file_location(plugin_id, plugin_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # 查找插件类
                    plugin_class = getattr(module, "Plugin", None)
                    if plugin_class and issubclass(plugin_class, PluginInterface):
                        plugin = plugin_class()
                        plugin.plugin_info = info
                        if plugin.on_load(config or {}):
                            self._plugins[plugin_id] = plugin
                            info.state = PluginState.LOADED
                            info.config = config or {}
                            info.loaded_at = int(time.time())
                            # 注册钩子
                            for hook_name, func in plugin.get_hooks().items():
                                self._register_hook(hook_name, plugin_id, func)
                            return True, "加载成功"
                        else:
                            info.state = PluginState.ERROR
                            info.error = "插件初始化失败"
                            return False, "插件初始化失败"
                else:
                    # 内置插件 - 仅标记为已加载
                    info.state = PluginState.LOADED
                    info.config = config or {}
                    info.loaded_at = int(time.time())
                    return True, "内置插件加载成功"

            except Exception as e:
                info.state = PluginState.ERROR
                info.error = str(e)
                return False, f"加载失败: {e}"

    def unload_plugin(self, plugin_id: str) -> bool:
        """卸载插件"""
        with self._lock:
            plugin = self._plugins.get(plugin_id)
            info = self._info.get(plugin_id)
            if not info:
                return False
            try:
                if plugin and hasattr(plugin, 'on_unload'):
                    plugin.on_unload()
                # 移除钩子
                for hook_list in self._hooks.values():
                    hook_list[:] = [(pid, f) for pid, f in hook_list if pid != plugin_id]
                self._plugins.pop(plugin_id, None)
                info.state = PluginState.UNLOADED
                return True
            except Exception:
                return False

    def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件"""
        with self._lock:
            plugin = self._plugins.get(plugin_id)
            info = self._info.get(plugin_id)
            if not info:
                return False
            if plugin and hasattr(plugin, 'on_enable'):
                plugin.on_enable()
            info.state = PluginState.ENABLED
            return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件"""
        with self._lock:
            plugin = self._plugins.get(plugin_id)
            info = self._info.get(plugin_id)
            if not info:
                return False
            if plugin and hasattr(plugin, 'on_disable'):
                plugin.on_disable()
            info.state = PluginState.DISABLED
            return True

    def _register_hook(self, hook_name: str, plugin_id: str, func: Callable):
        """注册钩子"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append((plugin_id, func))

    def execute_hooks(self, hook_name: str, data: Dict) -> Dict:
        """执行钩子"""
        with self._lock:
            hooks = self._hooks.get(hook_name, [])
            result = data.copy()
            for plugin_id, func in hooks:
                info = self._info.get(plugin_id)
                if info and info.state == PluginState.ENABLED:
                    try:
                        hook_result = func(result)
                        if hook_result:
                            result.update(hook_result)
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"插件 {plugin_id} 钩子 {hook_name} 执行失败: {e}")
            return result

    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        """获取插件信息"""
        return self._info.get(plugin_id)

    def get_all_plugins(self) -> List[PluginInfo]:
        """获取所有插件"""
        return list(self._info.values())

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[PluginInfo]:
        """按类型获取插件"""
        return [p for p in self._info.values() if p.plugin_type == plugin_type]

    def get_enabled_plugins(self) -> List[PluginInfo]:
        """获取已启用插件"""
        return [p for p in self._info.values() if p.state == PluginState.ENABLED]

    def scan_plugins(self) -> List[str]:
        """扫描插件目录"""
        new_plugins = []
        if os.path.isdir(self.plugins_dir):
            for filename in os.listdir(self.plugins_dir):
                if filename.endswith(".py") and not filename.startswith("_"):
                    plugin_id = filename[:-3]
                    if plugin_id not in self._info:
                        info = PluginInfo(
                            id=plugin_id,
                            name=plugin_id,
                            version="0.0.0",
                            description="外部插件",
                            author="Unknown",
                            plugin_type=PluginType.CUSTOM,
                        )
                        self._info[plugin_id] = info
                        new_plugins.append(plugin_id)
        return new_plugins

    def get_stats(self) -> Dict:
        """获取插件统计"""
        states = {}
        for p in self._info.values():
            state = p.state.value
            states[state] = states.get(state, 0) + 1
        return {
            "total": len(self._info),
            "states": states,
            "hooks": {name: len(funcs) for name, funcs in self._hooks.items()},
        }
