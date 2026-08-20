"""Claude Code environment detection, installation, update and diagnostics.

This module never configures provider credentials.  It only manages the Claude
Code executable and its PATH entry, so it is safe to use from the desktop UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import requests

from .path_resolver import ClaudeCommandResolver


OFFICIAL_INSTALLER_URL = "https://claude.ai/install.ps1"
OFFICIAL_INSTALLER_HOSTS = {"claude.ai", "www.claude.ai", "downloads.claude.ai"}
WINGET_PACKAGE_ID = "Anthropic.ClaudeCode"
ProgressCallback = Callable[[str, str, int], None]


@dataclass(frozen=True)
class ClaudeEnvironmentStatus:
    installed: bool
    executable: str = ""
    version: str = ""
    healthy: bool = False
    install_method: str = ""
    installations: Tuple[str, ...] = ()
    warning: str = ""
    diagnostics: str = ""


@dataclass(frozen=True)
class ClaudeInstallResult:
    success: bool
    code: str
    message: str
    status: ClaudeEnvironmentStatus
    output: str = ""
    steps: Tuple[str, ...] = field(default_factory=tuple)


class ClaudeEnvironmentManager:
    """Manage Claude Code without touching API keys or Claude provider config."""

    def __init__(self, home_dir: Optional[str] = None):
        self.home_dir = os.path.abspath(home_dir or os.path.expanduser("~"))

    def detect(self, run_doctor: bool = False) -> ClaudeEnvironmentStatus:
        candidates = self._candidate_installations()
        if not candidates:
            return ClaudeEnvironmentStatus(
                installed=False,
                warning="未检测到 Claude Code。可使用一键安装。",
            )

        executable = candidates[0]
        version_result = self._run([executable, "--version"], timeout=15)
        version_text = self._clean_output(version_result)
        healthy = version_result.returncode == 0 and "claude" in version_text.lower()
        diagnostics = ""
        if run_doctor and healthy:
            doctor = self._run([executable, "doctor"], timeout=45)
            diagnostics = self._clean_output(doctor)

        method = self._identify_method(executable)
        warning = ""
        if len(candidates) > 1:
            warning = (
                "检测到多个 Claude Code 安装，当前使用第一个 PATH 命中的版本。"
                "建议只保留一种安装方式，避免升级后仍启动旧版本。"
            )
        elif not healthy:
            warning = "找到了 Claude Code，但版本检查失败；可尝试修复环境或重新安装。"

        return ClaudeEnvironmentStatus(
            installed=True,
            executable=executable,
            version=version_text.splitlines()[0] if version_text else "版本未知",
            healthy=healthy,
            install_method=method,
            installations=tuple(candidates),
            warning=warning,
            diagnostics=diagnostics,
        )

    def install(self, progress: Optional[ProgressCallback] = None) -> ClaudeInstallResult:
        """Install Claude Code with WinGet, then the official native installer.

        The caller must run this method from a worker thread.  A visible UI
        button is the user's consent to start the installation.
        """
        steps: List[str] = []
        self._progress(progress, "detect", "正在检查 Claude Code 环境…", 5)
        current = self.detect()
        if current.healthy:
            return ClaudeInstallResult(
                True, "already_installed", f"Claude Code 已安装：{current.version}", current,
                steps=("检测到现有安装",),
            )

        winget = self._which_executable("winget.exe", "winget")
        if winget:
            self._progress(progress, "download", "正在通过 WinGet 下载 Claude Code…", 20)
            steps.append("使用 WinGet 官方软件源")
            command = [
                winget, "install", "--id", WINGET_PACKAGE_ID, "--exact",
                "--source", "winget", "--accept-package-agreements",
                "--accept-source-agreements", "--disable-interactivity",
            ]
            result = self._run(command, timeout=900)
            output = self._clean_output(result)
            if result.returncode == 0:
                self._activate_known_paths()
                status = self.detect(run_doctor=False)
                if status.healthy:
                    self._progress(progress, "verify", "Claude Code 安装并验证成功。", 100)
                    return ClaudeInstallResult(
                        True, "installed", f"安装成功：{status.version}", status,
                        output=output, steps=tuple(steps + ["版本检查通过"]),
                    )
                return ClaudeInstallResult(
                    False, "path_not_refreshed",
                    "安装程序已完成，但当前进程仍找不到 Claude Code。请点击“修复 PATH”，或重启本软件后再检测。",
                    status, output=output, steps=tuple(steps),
                )

            code, message = self._classify_failure(output, result.returncode, "winget")
            steps.append(f"WinGet 失败：{message}")
            self._progress(progress, "fallback", "WinGet 安装失败，正在尝试官方原生安装器…", 45)

        if not self._powershell_path():
            status = self.detect()
            return ClaudeInstallResult(
                False, "powershell_missing",
                "找不到 Windows PowerShell，无法运行官方安装器。请修复 Windows 系统组件后重试。",
                status, steps=tuple(steps),
            )

        native_result = self._install_native(progress, steps)
        return native_result

    def update(self, progress: Optional[ProgressCallback] = None) -> ClaudeInstallResult:
        current = self.detect()
        if not current.healthy:
            return self.install(progress)

        self._progress(progress, "update", "正在检查并安装 Claude Code 更新…", 20)
        if current.install_method == "winget" and self._which_executable("winget.exe", "winget"):
            winget = self._which_executable("winget.exe", "winget")
            result = self._run([
                winget, "upgrade", "--id", WINGET_PACKAGE_ID, "--exact",
                "--source", "winget", "--accept-package-agreements",
                "--accept-source-agreements", "--disable-interactivity",
            ], timeout=900)
        else:
            result = self._run([current.executable, "update"], timeout=900)

        output = self._clean_output(result)
        if result.returncode != 0:
            code, message = self._classify_failure(output, result.returncode, "update")
            return ClaudeInstallResult(False, code, message, self.detect(), output=output)

        self._activate_known_paths()
        status = self.detect()
        self._progress(progress, "verify", "更新完成。", 100)
        return ClaudeInstallResult(
            status.healthy,
            "updated" if status.healthy else "verify_failed",
            f"更新完成：{status.version}" if status.healthy else "更新命令已完成，但版本验证失败。",
            status,
            output=output,
        )

    def repair_path(self, persist: bool = True) -> ClaudeInstallResult:
        candidates = self._candidate_installations(include_path=False)
        if not candidates:
            status = self.detect()
            return ClaudeInstallResult(
                False, "not_installed", "没有找到可加入 PATH 的 Claude Code 安装。请先安装。", status
            )

        install_dir = os.path.dirname(candidates[0])
        self._prepend_process_path(install_dir)
        if persist:
            ok, message = self._persist_user_path(install_dir)
            if not ok:
                return ClaudeInstallResult(False, "path_write_failed", message, self.detect())

        status = self.detect()
        if status.healthy:
            return ClaudeInstallResult(
                True, "path_repaired", "PATH 已修复。新打开的终端会自动识别 Claude Code。", status
            )
        return ClaudeInstallResult(
            False, "verify_failed", "PATH 已更新，但 Claude Code 仍无法运行；请查看详细诊断。", status
        )

    def doctor(self) -> ClaudeEnvironmentStatus:
        return self.detect(run_doctor=True)

    def _install_native(
        self, progress: Optional[ProgressCallback], steps: List[str]
    ) -> ClaudeInstallResult:
        temp_path = ""
        try:
            self._progress(progress, "download", "正在从 Anthropic 官方地址下载安装器…", 55)
            response = requests.get(
                OFFICIAL_INSTALLER_URL,
                timeout=(10, 60),
                allow_redirects=True,
                headers={"User-Agent": "Claude-API-Switcher-V4"},
            )
            response.raise_for_status()
            final = urlparse(response.url)
            if final.scheme != "https" or (final.hostname or "").lower() not in OFFICIAL_INSTALLER_HOSTS:
                raise ValueError("安装器被重定向到非官方地址")
            content = response.content
            if not (500 <= len(content) <= 2_000_000):
                raise ValueError("安装器文件大小异常")
            lowered = content[:100_000].lower()
            if b"claude" not in lowered or b"download" not in lowered:
                raise ValueError("下载内容不像 Claude Code 安装器")

            with tempfile.NamedTemporaryFile(
                prefix="claude-code-installer-", suffix=".ps1", delete=False
            ) as file:
                file.write(content)
                temp_path = file.name

            steps.append("已从 claude.ai 获取官方原生安装器")
            self._progress(progress, "install", "正在运行官方原生安装器…", 72)
            result = self._run([
                self._powershell_path(), "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", temp_path, "latest",
            ], timeout=900)
            output = self._clean_output(result)
            if result.returncode != 0:
                code, message = self._classify_failure(output, result.returncode, "native")
                return ClaudeInstallResult(
                    False, code, message, self.detect(), output=output, steps=tuple(steps)
                )

            self._activate_known_paths()
            status = self.detect()
            if not status.healthy:
                return ClaudeInstallResult(
                    False, "path_not_refreshed",
                    "官方安装器已完成，但未通过版本验证。请点击“修复 PATH”后重试。",
                    status, output=output, steps=tuple(steps),
                )
            self._progress(progress, "verify", "Claude Code 安装并验证成功。", 100)
            return ClaudeInstallResult(
                True, "installed", f"安装成功：{status.version}", status,
                output=output, steps=tuple(steps + ["版本检查通过"]),
            )
        except requests.Timeout:
            return ClaudeInstallResult(
                False, "network_timeout",
                "下载超时。请检查网络、代理或防火墙是否允许访问 claude.ai，然后重试。",
                self.detect(), steps=tuple(steps),
            )
        except requests.RequestException as exc:
            return ClaudeInstallResult(
                False, "network_error",
                f"下载安装器失败：{self._safe_exception(exc)}。请检查网络或代理设置。",
                self.detect(), steps=tuple(steps),
            )
        except (OSError, ValueError) as exc:
            return ClaudeInstallResult(
                False, "installer_invalid",
                f"官方安装器校验或保存失败：{self._safe_exception(exc)}。",
                self.detect(), steps=tuple(steps),
            )
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _candidate_installations(self, include_path: bool = True) -> List[str]:
        candidates: List[str] = []
        if include_path:
            resolved = ClaudeCommandResolver.resolve()
            if resolved:
                candidates.append(resolved)

        local = Path(self.home_dir) / ".local" / "bin" / "claude.exe"
        appdata_local = os.environ.get("LOCALAPPDATA", "")
        winget_link = Path(appdata_local) / "Microsoft" / "WinGet" / "Links" / "claude.exe"
        appdata_roaming = os.environ.get("APPDATA", "")
        npm_cmd = Path(appdata_roaming) / "npm" / "claude.cmd"
        for path in (local, winget_link, npm_cmd):
            text = os.path.abspath(str(path))
            if os.path.isfile(text) and text not in candidates:
                candidates.append(text)
        return candidates

    def _activate_known_paths(self) -> None:
        for path in self._candidate_installations(include_path=False):
            self._prepend_process_path(os.path.dirname(path))

    @staticmethod
    def _prepend_process_path(directory: str) -> None:
        items = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
        normalized = os.path.normcase(os.path.abspath(directory))
        if all(os.path.normcase(os.path.abspath(item)) != normalized for item in items):
            os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")

    @staticmethod
    def _persist_user_path(directory: str) -> Tuple[bool, str]:
        if os.name != "nt":
            return False, "自动修复 PATH 仅支持 Windows。"
        try:
            import winreg
            key_path = r"Environment"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
            ) as key:
                try:
                    current, value_type = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    current, value_type = "", winreg.REG_EXPAND_SZ
                entries = [item for item in str(current).split(";") if item]
                normalized = os.path.normcase(os.path.abspath(directory))
                if all(os.path.normcase(os.path.abspath(item)) != normalized for item in entries):
                    entries.insert(0, directory)
                    winreg.SetValueEx(key, "Path", 0, value_type, ";".join(entries))
            return True, "PATH 已更新"
        except OSError as exc:
            return False, f"无法写入当前用户 PATH：{ClaudeEnvironmentManager._safe_exception(exc)}"

    @staticmethod
    def _identify_method(path: str) -> str:
        lowered = path.lower().replace("/", "\\")
        if "\\microsoft\\winget\\" in lowered:
            return "winget"
        if "\\.local\\bin\\" in lowered:
            return "native"
        if "\\appdata\\roaming\\npm\\" in lowered:
            return "npm"
        return "unknown"

    @staticmethod
    def _which_executable(*names: str) -> str:
        for name in names:
            path = shutil.which(name)
            if path and os.path.isfile(path):
                return os.path.abspath(path)
        return ""

    @staticmethod
    def _powershell_path() -> str:
        return ClaudeEnvironmentManager._which_executable("powershell.exe", "pwsh.exe", "powershell", "pwsh")

    @staticmethod
    def _run(command: Sequence[str], timeout: int) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                list(command), capture_output=True, text=True, errors="replace",
                timeout=timeout, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return subprocess.CompletedProcess(command, 124, stdout, stderr + "\noperation timed out")
        except OSError as exc:
            return subprocess.CompletedProcess(command, 127, "", str(exc))

    @staticmethod
    def _clean_output(result: subprocess.CompletedProcess) -> str:
        text = "\n".join(part for part in (result.stdout, result.stderr) if part)
        return text.strip()[-12_000:]

    @staticmethod
    def _classify_failure(output: str, returncode: int, source: str) -> Tuple[str, str]:
        lowered = output.lower()
        if returncode == 124 or any(word in lowered for word in ("timed out", "timeout")):
            return "network_timeout", "操作超时。请检查网络、代理或防火墙后重试。"
        if any(word in lowered for word in (
            "unable to connect", "connection", "name resolution", "resolve host",
            "network", "0x801901", "403", "proxy",
        )):
            return "network_error", "无法连接安装源。请检查网络、代理和防火墙设置。"
        if any(word in lowered for word in (
            "access is denied", "permission denied", "0x80070005", "administrator",
        )):
            return "permission_denied", "权限不足。请关闭占用程序后重试；如系统要求，再以管理员身份运行。"
        if any(word in lowered for word in ("being used", "in use", "0x80070020", "file is locked")):
            return "file_locked", "Claude Code 正在运行或文件被占用。请关闭 Claude 窗口后重试更新。"
        if "no package found" in lowered or "no applicable" in lowered:
            return "package_unavailable", "当前 WinGet 软件源没有可用安装包，已保留官方安装器作为备用方式。"
        if "execution policy" in lowered:
            return "execution_policy", "PowerShell 执行策略阻止了安装器。请检查企业或系统策略。"
        return "install_failed", f"{source} 安装失败（错误码 {returncode}）。请展开详细信息查看原始输出后重试。"

    @staticmethod
    def _safe_exception(exc: BaseException) -> str:
        return str(exc).replace("\r", " ").replace("\n", " ")[:240]

    @staticmethod
    def _progress(callback: Optional[ProgressCallback], stage: str, message: str, percent: int) -> None:
        if callback:
            callback(stage, message, max(0, min(100, percent)))
