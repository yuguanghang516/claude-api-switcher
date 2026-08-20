"""以会话级环境变量安全启动 Claude Code。"""
import os
import shutil
import subprocess
from typing import Tuple

from .path_resolver import ClaudeCommandResolver


class ClaudeLauncher:
    """不写临时脚本、不修改全局 Claude 配置的启动器。"""

    @staticmethod
    def launch(
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        small_fast_model: str,
        project_dir: str,
        claude_path: str = "",
        auth_mode: str = "bearer",
    ) -> Tuple[bool, str]:
        if not base_url:
            return False, "未设置 API Base URL"
        if not api_key:
            return False, "未设置 API Key"
        if not model:
            return False, "未设置模型名称"
        if not project_dir:
            return False, "未选择项目目录"
        if not os.path.isdir(project_dir):
            return False, f"项目目录不存在：{project_dir}"
        claude_path = claude_path or ClaudeCommandResolver.resolve()
        if not claude_path or not os.path.isfile(claude_path):
            return False, "找不到 Claude Code；已检查 PATH、npm 和 ~/.local/bin"
        # 优先使用 Windows Terminal (wt.exe)，完美支持 Ctrl+V 粘贴
        # 其次使用 cmd.exe（右键标题栏可粘贴）
        wt_path = shutil.which("wt.exe")
        cmd_path = shutil.which("cmd.exe")
        if not cmd_path:
            system_root = os.environ.get("SystemRoot")
            if system_root:
                cmd_path = os.path.join(system_root, "System32", "cmd.exe")
        if not wt_path and not cmd_path:
            return False, "找不到终端，无法打开 Claude"

        child_env = os.environ.copy()
        # Claude Code 中 AUTH_TOKEN 表示 Bearer，API_KEY 表示 x-api-key。
        # 先移除父进程遗留值，避免两种认证方式互相抢占。
        child_env.pop("ANTHROPIC_AUTH_TOKEN", None)
        child_env.pop("ANTHROPIC_API_KEY", None)
        # 空字符串也要显式传入，用来覆盖 ~/.claude/settings.json 中可能
        # 保存的另一套认证变量；Claude Code 对进程环境的优先级更高。
        credential_env = (
            {"ANTHROPIC_API_KEY": api_key, "ANTHROPIC_AUTH_TOKEN": ""}
            if auth_mode == "x-api-key"
            else {"ANTHROPIC_AUTH_TOKEN": api_key, "ANTHROPIC_API_KEY": ""}
        )
        child_env.update({
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_SMALL_FAST_MODEL": small_fast_model or model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "CLAUDE_SWITCHER_CLAUDE_PATH": claude_path,
        })
        child_env.update(credential_env)

        # 命令行中没有 Key；敏感信息只存在于新进程环境中。
        # Windows Terminal 支持 Ctrl+V 粘贴
        if wt_path:
            command = [
                wt_path,
                "new-tab",
                "--title", "Claude Code",
                cmd_path or "cmd.exe", "/K", claude_path,
            ]
        else:
            command = [
                cmd_path,
                "/K",
                f"title Claude Code && {claude_path}",
            ]
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        try:
            subprocess.Popen(
                command,
                cwd=project_dir,
                env=child_env,
                shell=False,
                creationflags=creationflags,
            )
            return True, (
                f"已启动 Claude Code（{provider_name}，仅当前窗口生效） · "
                f"目录: {project_dir} · 命令: {claude_path}"
            )
        except FileNotFoundError:
            return False, "找不到命令提示符，无法启动 Claude Code"
        except Exception as exc:
            return False, f"启动失败：{str(exc)[:100]}"
