"""以会话级环境变量安全启动 Claude Code。"""
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from .path_resolver import ClaudeCommandResolver


class ClaudeLauncher:
    """不写临时脚本、不修改全局 Claude 配置的启动器。"""

    _ROUTING_ENV_KEYS = {
        "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDE_CODE_USE_VERTEX",
    }
    _MAX_SETTINGS_BYTES = 1024 * 1024

    @classmethod
    def _settings_source_is_clean(cls, path: Path) -> bool:
        """Inspect only routing keys; never return or log setting values."""
        if not path.exists():
            return True
        try:
            if not path.is_file() or path.stat().st_size > cls._MAX_SETTINGS_BYTES:
                return False
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        if str(payload.get("model") or "").strip() or payload.get("apiKeyHelper"):
            return False
        env = payload.get("env") or {}
        if not isinstance(env, dict):
            return False
        for key in env:
            normalized = str(key or "").strip().upper()
            if normalized.startswith("ANTHROPIC_") or normalized in cls._ROUTING_ENV_KEYS:
                return False
        return True

    @classmethod
    def select_setting_source(cls, project_dir: str) -> Tuple[str, str]:
        """Choose one Claude settings source that cannot override API routing."""
        settings_dir = Path(project_dir) / ".claude"
        candidates = (
            ("local", settings_dir / "settings.local.json"),
            ("project", settings_dir / "settings.json"),
        )
        unsafe = []
        for source, path in candidates:
            if cls._settings_source_is_clean(path):
                return source, ""
            unsafe.append(path.name)
        return "", (
            "项目中的 Claude 设置同时包含旧 API 路由或文件格式异常："
            f"{', '.join(unsafe)}。请移除其中的 ANTHROPIC_*、model 或 apiKeyHelper，"
            "再由本软件启动；全局设置不会被修改。"
        )

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
        setting_source, setting_error = ClaudeLauncher.select_setting_source(project_dir)
        if not setting_source:
            return False, setting_error
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
        # 清除父进程中的旧供应商路由。空字符串仍会被 Claude Code 当作
        # “已设置”，因此未使用的认证变量必须完全不存在。
        for name in (
            "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
        ):
            child_env.pop(name, None)
        credential_env = (
            {"ANTHROPIC_API_KEY": api_key}
            if auth_mode == "x-api-key"
            else {"ANTHROPIC_AUTH_TOKEN": api_key}
        )
        child_env.update({
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_SMALL_FAST_MODEL": small_fast_model or model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": small_fast_model or model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "CLAUDE_SWITCHER_CLAUDE_PATH": claude_path,
        })
        # Claude Code 会把 ~/.claude/settings.json 中的 env 配置覆盖到进程环境。
        # 给软件启动的会话使用独立状态目录，并排除 user/project 设置源，避免
        # 全局 LongCat 等旧路由重新覆盖用户刚选择的供应商。API Key 仍只在
        # 子进程环境中，不会写入这个目录或出现在命令行。
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
        child_env["CLAUDE_CONFIG_DIR"] = os.path.join(
            local_app_data, "ClaudeAPISwitcher", "claude-session")
        child_env.update(credential_env)

        # 命令行中没有 Key；敏感信息只存在于新进程环境中。
        # Windows Terminal 支持 Ctrl+V 粘贴
        if wt_path:
            command = [
                wt_path,
                "-w", "new",
                "new-tab",
                "--title", f"Claude Code · {provider_name}",
                cmd_path or "cmd.exe", "/K", claude_path,
                "--setting-sources", setting_source,
            ]
        else:
            command = [
                cmd_path,
                "/K",
                f'title Claude Code && call "{claude_path}" --setting-sources {setting_source}',
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
