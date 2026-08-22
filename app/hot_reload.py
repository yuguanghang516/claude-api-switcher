"""
V2 无重启热切换模块
支持修改以下内容无需重启服务：
- API Key
- 模型
- 路由规则
- 通知设置
"""
import os
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass


@dataclass
class ConfigFile:
    """监控的配置文件"""
    path: str
    last_modified: float = 0
    last_size: int = 0


class HotReloader:
    """热切换管理器"""

    def __init__(self, watch_interval: int = 2, logger=None):
        """
        :param watch_interval: 监控间隔（秒）
        """
        self._watched_files: Dict[str, ConfigFile] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._global_callbacks: List[Callable] = []
        self._watch_interval = watch_interval
        self._logger = logger
        self._running = False
        self._watcher_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def watch_file(self, file_path: str, on_change: Callable = None):
        """
        添加监控文件
        :param file_path: 文件路径
        :param on_change: 变更回调 (path, old_mtime, new_mtime)
        """
        with self._lock:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                self._watched_files[file_path] = ConfigFile(
                    path=file_path,
                    last_modified=stat.st_mtime,
                    last_size=stat.st_size,
                )
            else:
                self._watched_files[file_path] = ConfigFile(path=file_path)

            if on_change:
                if file_path not in self._callbacks:
                    self._callbacks[file_path] = []
                self._callbacks[file_path].append(on_change)

    def unwatch_file(self, file_path: str):
        """取消监控文件"""
        with self._lock:
            self._watched_files.pop(file_path, None)
            self._callbacks.pop(file_path, None)

    def on_any_change(self, callback: Callable):
        """注册全局变更回调"""
        self._global_callbacks.append(callback)

    def start(self):
        """启动热切换监控"""
        if self._running:
            return
        self._running = True
        self._watcher_thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="hot-reloader"
        )
        self._watcher_thread.start()
        if self._logger:
            self._logger.info("热切换监控已启动")

    def stop(self):
        """停止热切换监控"""
        self._running = False
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5)
            self._watcher_thread = None
        if self._logger:
            self._logger.info("热切换监控已停止")

    def _watch_loop(self):
        """监控循环"""
        while self._running:
            self._check_files()
            time.sleep(self._watch_interval)

    def _check_files(self):
        """检查文件变更"""
        with self._lock:
            files = dict(self._watched_files)

        for path, config_file in files.items():
            if not os.path.exists(path):
                continue

            try:
                stat = os.stat(path)
                if (stat.st_mtime != config_file.last_modified or
                        stat.st_size != config_file.last_size):
                    old_mtime = config_file.last_modified
                    config_file.last_modified = stat.st_mtime
                    config_file.last_size = stat.st_size

                    # 更新缓存
                    with self._lock:
                        self._watched_files[path] = config_file

                    # 触发回调
                    self._fire_callbacks(path, old_mtime, stat.st_mtime)
            except OSError:
                pass

    def _fire_callbacks(self, path: str, old_mtime: float, new_mtime: float):
        """触发变更回调"""
        # 文件级回调
        callbacks = self._callbacks.get(path, [])
        for cb in callbacks:
            try:
                cb(path, old_mtime, new_mtime)
            except Exception as e:
                if self._logger:
                    self._logger.error(f"热切换回调异常: {e}")

        # 全局回调
        for cb in self._global_callbacks:
            try:
                cb(path, old_mtime, new_mtime)
            except Exception as e:
                if self._logger:
                    self._logger.error(f"热切换全局回调异常: {e}")

        if self._logger:
            self._logger.info(f"配置文件已变更: {path}")

    def get_watched_files(self) -> List[str]:
        """获取所有监控的文件"""
        with self._lock:
            return list(self._watched_files.keys())

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running


class ConfigHotSwapper:
    """配置热切换器 - 整合所有配置的热切换"""

    def __init__(self, v2_config, db_manager=None, logger=None):
        """
        :param v2_config: V2ConfigManager 实例
        :param db_manager: DatabaseManager 实例
        :param logger: 日志器
        """
        self.v2_config = v2_config
        self.db = db_manager
        self.logger = logger
        self._reloader = HotReloader(watch_interval=2, logger=logger)
        self._change_handlers: Dict[str, Callable] = {}
        self._setup_watchers()

    def _setup_watchers(self):
        """设置文件监控"""
        # 监控 V2 配置文件
        v2_config_path = self.v2_config.config_file
        self._reloader.watch_file(v2_config_path, self._on_v2_config_change)

        # 监控主配置文件
        if hasattr(self.v2_config, 'data_dir'):
            main_config = os.path.join(self.v2_config.data_dir, "config.json")
            if os.path.exists(main_config):
                self._reloader.watch_file(main_config, self._on_main_config_change)

    def _on_v2_config_change(self, path: str, old_mtime: float, new_mtime: float):
        """V2 配置变更处理"""
        if self.logger:
            self.logger.info("检测到 V2 配置变更，正在重新加载...")
        self.v2_config.reload()
        self._fire_handler("v2_config", path)

    def _on_main_config_change(self, path: str, old_mtime: float, new_mtime: float):
        """主配置变更处理"""
        if self.logger:
            self.logger.info("检测到主配置变更，正在重新加载...")
        self._fire_handler("main_config", path)

    def register_handler(self, config_type: str, handler: Callable):
        """
        注册配置变更处理器
        :param config_type: 配置类型 (v2_config, main_config, models, routing)
        :param handler: 处理函数
        """
        self._change_handlers[config_type] = handler

    def _fire_handler(self, config_type: str, path: str):
        """触发处理器"""
        handler = self._change_handlers.get(config_type)
        if handler:
            try:
                handler(path)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"配置处理器异常: {e}")

    def start(self):
        """启动热切换"""
        self._reloader.start()

    def stop(self):
        """停止热切换"""
        self._reloader.stop()

    def reload_now(self):
        """立即重新加载所有配置"""
        self.v2_config.reload()
        if self.logger:
            self.logger.info("配置已手动重新加载")

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._reloader.is_running()
