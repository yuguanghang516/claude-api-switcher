"""
Claude API Switcher V4
主入口文件

功能：
1. 管理并一键切换 Claude Code 使用的第三方 API（原有功能）
2. 本地 AI 网关 - OpenAI API 兼容接口（新增 V1 功能）
3. 多模型供应商管理
4. Token 统计与使用日志
"""
import os
import sys
import shutil

# 确保 app 包在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui import MainWindow
from app.single_instance import SingleInstanceGuard
from app.version import APP_VERSION_NAME


def get_base_dir() -> str:
    """获取程序基础目录"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        return os.path.dirname(sys.executable)
    else:
        # 普通 Python 运行
        return os.path.dirname(os.path.abspath(__file__))


def get_state_dir() -> str:
    """运行数据固定放到用户 LocalAppData，不跟着 EXE 或源码目录移动。"""
    override = os.environ.get("CLAUDE_SWITCHER_DATA_DIR")
    if override:
        return os.path.abspath(override)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(local_app_data, "ClaudeAPISwitcher")


def migrate_legacy_config(base_dir: str, data_dir: str):
    """只迁移旧版非敏感 config.json；日志和私人备份不进入发布目录。"""
    target = os.path.join(data_dir, "config.json")
    legacy = os.path.join(base_dir, "data", "config.json")
    if not os.path.exists(target) and os.path.isfile(legacy):
        os.makedirs(data_dir, exist_ok=True)
        shutil.copy2(legacy, target)


def main():
    """主函数"""
    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire():
        return
    base_dir = get_base_dir()

    state_dir = get_state_dir()
    data_dir = os.path.join(state_dir, "data")
    logs_dir = os.path.join(state_dir, "logs")

    if getattr(sys, "frozen", False):
        migrate_legacy_config(base_dir, data_dir)

    # 确保目录存在
    for d in [data_dir, logs_dir]:
        os.makedirs(d, exist_ok=True)

    # 创建并运行主窗口
    try:
        app = MainWindow(data_dir, logs_dir)
        app.run()
    finally:
        instance_guard.release()


if __name__ == "__main__":
    main()
