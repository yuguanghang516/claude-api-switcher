"""Safe lifecycle and connectivity management for the optional gcli2api service."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:7861"
REPO_URL = "https://github.com/su-kaka/gcli2api.git"
WINGET_PACKAGES: Tuple[Tuple[str, str], ...] = (
    ("Git.Git", "git"),
    ("astral-sh.uv", "uv"),
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
PLACEHOLDER_PASSWORD = "YOUR_GCLI2API_PASSWORD"


@dataclass(frozen=True)
class Gcli2ApiStatus:
    """Immutable snapshot used by the UI and tests."""

    state: str = "unknown"
    installed: bool = False
    running: bool = False
    ready: bool = False
    base_url: str = DEFAULT_BASE_URL
    install_dir: Path = Path()
    version: str = ""
    models: Tuple[str, ...] = ()
    error_code: str = ""
    message: str = ""


class Gcli2ApiManager:
    """Manage an optional, separately licensed gcli2api checkout.

    The manager never downloads credentials, runs remote script text, changes the
    PowerShell execution policy, or terminates processes it did not start.
    """

    def __init__(self, data_dir: Path | str, base_url: str = DEFAULT_BASE_URL,
                 logger=None, request_timeout: int = 6,
                 auto_discover: bool = True) -> None:
        self.data_dir = Path(data_dir)
        self.base_url = self.normalize_base_url(base_url)
        self.managed_install_dir = self.data_dir / "integrations" / "gcli2api"
        self.install_dir = self.managed_install_dir
        self.logger = logger
        self.request_timeout = request_timeout
        self.auto_discover = auto_discover
        self._managed_process: Optional[subprocess.Popen] = None
        self._managed_executable = ""
        if auto_discover:
            self.refresh_install_dir()

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        value = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        if not Gcli2ApiManager.validate_base_url(value):
            raise ValueError("本地地址可使用 HTTP；远程 gcli2api 地址必须使用 HTTPS")
        return value

    @staticmethod
    def validate_base_url(base_url: str) -> bool:
        parsed = urlparse((base_url or "").strip())
        host = (parsed.hostname or "").lower()
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        if parsed.scheme == "http":
            return host in LOCAL_HOSTS
        return parsed.scheme == "https" and bool(host)

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/v1/models"

    @property
    def is_local(self) -> bool:
        return (urlparse(self.base_url).hostname or "").lower() in LOCAL_HOSTS

    def _safe_install_dir(self) -> Path:
        integration_root = (self.data_dir / "integrations").resolve()
        target = self.managed_install_dir.resolve()
        try:
            target.relative_to(integration_root)
        except ValueError as exc:
            raise ValueError("gcli2api 安装目录超出应用数据目录") from exc
        if target == integration_root:
            raise ValueError("gcli2api 安装目录无效")
        return target

    @staticmethod
    def _is_complete_install(path: Path) -> bool:
        """Return whether a directory is a runnable Windows gcli2api checkout."""
        return (
            path.is_dir()
            and (path / "web.py").is_file()
            and (path / "pyproject.toml").is_file()
            and (path / ".venv" / "Scripts" / "python.exe").is_file()
        )

    def candidate_install_dirs(self) -> Tuple[Path, ...]:
        """List explicit, bounded locations used by supported Windows installers."""
        profile = Path(os.environ.get("USERPROFILE") or Path.home())
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or profile / "AppData" / "Local")
        roaming_app_data = Path(os.environ.get("APPDATA") or profile / "AppData" / "Roaming")
        configured = os.environ.get("GCLI2API_HOME", "").strip()
        values = [
            self.managed_install_dir,
            Path(configured) if configured else None,
            profile / "gcli2api",
            profile / "Desktop" / "gcli2api",
            profile / "Documents" / "gcli2api",
            local_app_data / "gcli2api",
            roaming_app_data / "gcli2api",
        ]
        result: List[Path] = []
        seen = set()
        for value in values:
            if value is None:
                continue
            try:
                resolved = value.expanduser().resolve()
            except OSError:
                continue
            normalized = os.path.normcase(str(resolved))
            if normalized not in seen:
                seen.add(normalized)
                result.append(resolved)
        return tuple(result)

    def refresh_install_dir(self) -> Path:
        """Use an existing terminal installation before the app-managed location."""
        if not self.auto_discover:
            return self.install_dir
        for candidate in self.candidate_install_dirs():
            if self._is_complete_install(candidate):
                self.install_dir = candidate
                return candidate
        self.install_dir = self.managed_install_dir
        return self.install_dir

    @staticmethod
    def _resolve_executable(name: str) -> str:
        found = shutil.which(name)
        if found:
            return found
        candidates: Dict[str, Sequence[Path]] = {
            "git": (
                Path(os.environ.get("ProgramFiles", "")) / "Git" / "cmd" / "git.exe",
                Path(os.environ.get("ProgramFiles(x86)", "")) / "Git" / "cmd" / "git.exe",
            ),
            "uv": (
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "uv.exe",
                Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "uv.exe",
            ),
            "winget": (
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "winget.exe",
            ),
        }
        for candidate in candidates.get(name, ()):
            if str(candidate) and candidate.is_file():
                return str(candidate)
        return ""

    def detect_dependencies(self) -> Dict[str, bool]:
        return {name: bool(self._resolve_executable(name)) for name in ("git", "uv", "winget")}

    def build_dependency_install_commands(self) -> List[List[str]]:
        dependencies = self.detect_dependencies()
        if not dependencies["winget"]:
            return []
        winget = self._resolve_executable("winget") or "winget"
        commands: List[List[str]] = []
        for package_id, executable in WINGET_PACKAGES:
            if not dependencies[executable]:
                commands.append([
                    winget, "install", "--id", package_id, "--exact", "--silent",
                    "--accept-package-agreements", "--accept-source-agreements",
                ])
        return commands

    @staticmethod
    def _creation_flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def _run_command(self, args: Sequence[str], cwd: Optional[Path] = None,
                     timeout: int = 600) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(args), cwd=str(cwd) if cwd else None, shell=False,
            capture_output=True, text=True, timeout=timeout,
            creationflags=self._creation_flags(), check=False,
        )

    def _command_error(self, label: str, result: subprocess.CompletedProcess,
                       secrets: Iterable[str] = ()) -> str:
        detail = (result.stderr or result.stdout or "未知错误").strip()
        return f"{label}失败（退出码 {result.returncode}）：{self._redact(detail, secrets)[:300]}"

    def install(self, progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Install dependencies and clone/sync the upstream project after UI consent."""

        progress = progress_callback or (lambda _message: None)
        existing = self.refresh_install_dir()
        if self._is_complete_install(existing):
            return True, f"已检测到现有 gcli2api，无需重复安装：{existing}"
        try:
            target = self._safe_install_dir()
            self.install_dir = target
            target.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            return False, self._redact(str(exc))

        dependencies = self.detect_dependencies()
        missing = [name for name in ("git", "uv") if not dependencies[name]]
        if missing and not dependencies["winget"]:
            return False, f"缺少 {', '.join(missing)}，且未找到 WinGet；请先安装 Git 和 uv"

        for command in self.build_dependency_install_commands():
            package_id = command[command.index("--id") + 1]
            progress(f"正在通过 WinGet 安装 {package_id}…")
            try:
                result = self._run_command(command, timeout=900)
            except subprocess.TimeoutExpired:
                return False, f"安装 {package_id} 超时；请检查网络或 WinGet 源"
            except OSError as exc:
                return False, f"无法启动 WinGet：{self._redact(str(exc))}"
            if result.returncode != 0:
                return False, self._command_error(f"安装 {package_id}", result)

        git = self._resolve_executable("git")
        uv = self._resolve_executable("uv")
        if not git or not uv:
            return False, "依赖已安装但当前进程尚未找到 Git 或 uv；请重开软件后重试"

        web_file = target / "web.py"
        if not web_file.is_file():
            if target.exists() and any(target.iterdir()):
                return False, f"安装目录已存在但不是完整 gcli2api：{target}"
            progress("正在从 GitHub 下载 gcli2api…")
            try:
                result = self._run_command([git, "clone", "--depth", "1", REPO_URL, str(target)], timeout=900)
            except subprocess.TimeoutExpired:
                return False, "下载 gcli2api 超时；请检查 GitHub、代理或 DNS"
            except OSError as exc:
                return False, f"无法启动 Git：{self._redact(str(exc))}"
            if result.returncode != 0:
                return False, self._command_error("下载 gcli2api", result)

        progress("正在同步 gcli2api 依赖…")
        try:
            result = self._run_command([uv, "sync"], cwd=target, timeout=1200)
        except subprocess.TimeoutExpired:
            return False, "gcli2api 依赖同步超时；请检查网络、代理或 PyPI 连接"
        except OSError as exc:
            return False, f"无法启动 uv：{self._redact(str(exc))}"
        if result.returncode != 0:
            return False, self._command_error("同步 gcli2api 依赖", result)
        if not (target / ".venv" / "Scripts" / "python.exe").is_file():
            return False, "依赖同步完成，但未找到受管 Python 环境"
        return True, f"gcli2api 已安装到 {target}"

    def _version(self) -> str:
        target = self.install_dir
        if not (target / ".git").exists():
            return ""
        git = self._resolve_executable("git")
        if not git:
            return ""
        try:
            result = self._run_command([git, "rev-parse", "--short", "HEAD"], cwd=target, timeout=5)
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    @staticmethod
    def _extract_models(payload: object) -> Tuple[str, ...]:
        if not isinstance(payload, dict):
            return ()
        data = payload.get("data", [])
        if not isinstance(data, list):
            return ()
        names = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                name = item["id"].strip()
                if name and name not in names:
                    names.append(name)
        return tuple(names)

    def _status(self, **changes) -> Gcli2ApiStatus:
        base = {
            "base_url": self.base_url,
            "install_dir": self.install_dir,
            "installed": (self.install_dir / "web.py").is_file(),
            "version": self._version(),
        }
        base.update(changes)
        return Gcli2ApiStatus(**base)

    def detect(self, api_password: str = "") -> Gcli2ApiStatus:
        """Probe the service without following credential-bearing redirects."""

        if self.is_local:
            self.refresh_install_dir()
        headers = {"Accept": "application/json"}
        if api_password:
            headers["Authorization"] = f"Bearer {api_password}"
        try:
            response = requests.get(
                self.models_url, headers=headers, timeout=self.request_timeout,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            return self._status(state="error", error_code="timeout", message="连接超时；请检查代理、防火墙和服务日志")
        except requests.exceptions.ConnectionError as exc:
            detail = str(exc).lower()
            if any(marker in detail for marker in ("getaddrinfo", "name resolution", "enotfound")):
                return self._status(state="error", error_code="dns", message="找不到服务器；请检查地址、网络或 DNS")
            if (self.install_dir / "web.py").is_file() and self.is_local:
                return self._status(state="stopped", error_code="connection_refused", message="gcli2api 已安装，但服务未启动")
            return self._status(state="not_installed", error_code="connection_refused", message="未检测到 gcli2api 服务")
        except requests.exceptions.RequestException:
            return self._status(state="error", error_code="request_error", message="请求异常；凭据未泄露")

        status = response.status_code
        if 300 <= status < 400:
            return self._status(state="error", running=True, error_code="redirect", message="服务返回重定向；为保护密码已停止")
        if status == 401:
            return self._status(state="auth_required", running=True, error_code="auth_failed", message="API 密码错误或尚未填写；API_PASSWORD 与面板密码可以不同")
        if status == 403:
            return self._status(state="error", running=True, error_code="forbidden", message="Google 账号、项目或凭据无权限")
        if status == 404:
            return self._status(state="error", running=True, error_code="not_found", message="API 地址或 /v1/models 端点不存在")
        if status == 429:
            return self._status(state="error", running=True, error_code="rate_limited", message="凭据额度不足或请求受限；请到管理面板检查凭据")
        if status >= 500:
            return self._status(state="error", running=True, error_code="server_error", message=f"gcli2api 服务暂时不可用（HTTP {status}）")
        if status != 200:
            return self._status(state="error", running=True, error_code="http_error", message=f"检测失败（HTTP {status}）")
        try:
            models = self._extract_models(response.json())
        except ValueError:
            return self._status(state="error", running=True, error_code="invalid_json", message="模型接口返回了无效 JSON")
        if not models:
            return self._status(state="oauth_required", running=True, error_code="no_models", message="服务已运行，但没有可用模型；请在面板完成 Google OAuth")
        return self._status(state="ready", running=True, ready=True, models=models,
                            message=f"可以调用 · {len(models)} 个模型")

    @staticmethod
    def select_models(models: Sequence[str]) -> Tuple[str, str]:
        clean = [str(model).strip() for model in models if str(model).strip()]
        gemini = [model for model in clean if "gemini" in model.lower()]
        primary = next((model for model in gemini if "pro" in model.lower()), "")
        if not primary:
            primary = gemini[0] if gemini else (clean[0] if clean else "gemini-2.5-pro")
        fast = next((model for model in gemini if "flash" in model.lower()), primary)
        return primary, fast

    def start(self, api_password: str = "", panel_password: str = "") -> Tuple[bool, str]:
        if not self.is_local:
            return False, "远程 gcli2api 只能连接，不能由本软件启动"
        self.refresh_install_dir()
        target = self._safe_install_dir()
        if self.install_dir != self.managed_install_dir:
            target = self.install_dir
        python_exe = target / ".venv" / "Scripts" / "python.exe"
        web_file = target / "web.py"
        if not python_exe.is_file() or not web_file.is_file():
            return False, "gcli2api 未完整安装，请先执行安装"
        if self._managed_process and self._managed_process.poll() is None:
            return True, f"gcli2api 已由本软件启动（PID {self._managed_process.pid}）"
        parsed = urlparse(self.base_url)
        child_env = os.environ.copy()
        child_env["HOST"] = "127.0.0.1"
        child_env["PORT"] = str(parsed.port or 7861)
        if api_password:
            child_env["API_PASSWORD"] = api_password
        if panel_password:
            child_env["PANEL_PASSWORD"] = panel_password
        try:
            process = subprocess.Popen(
                [str(python_exe), str(web_file)], cwd=str(target), env=child_env,
                shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=self._creation_flags(),
            )
        except OSError as exc:
            return False, f"启动 gcli2api 失败：{self._redact(str(exc), (api_password, panel_password))}"
        self._managed_process = process
        self._managed_executable = str(python_exe.resolve())
        return True, f"gcli2api 正在启动（PID {process.pid}）"

    def stop_managed(self) -> Tuple[bool, str]:
        process = self._managed_process
        if not process:
            return False, "没有由本软件启动的 gcli2api 进程"
        if process.poll() is not None:
            self._managed_process = None
            self._managed_executable = ""
            return True, "gcli2api 进程已经结束"
        args = process.args if isinstance(process.args, (list, tuple)) else []
        if not args or str(Path(str(args[0])).resolve()) != self._managed_executable:
            return False, "进程身份不匹配，已拒绝停止"
        try:
            process.terminate()
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            return False, "gcli2api 未在规定时间内退出；未强制结束进程"
        except OSError as exc:
            return False, f"停止失败：{self._redact(str(exc))}"
        finally:
            if process.poll() is not None:
                self._managed_process = None
                self._managed_executable = ""
        return True, "已停止由本软件启动的 gcli2api"

    def open_panel(self) -> bool:
        return bool(webbrowser.open(self.base_url))

    def generate_examples(self, model: str = "gemini-2.5-pro") -> Dict[str, str]:
        base = self.base_url
        openai_base = f"{base}/v1"
        return {
            "anthropic": (
                f'$env:ANTHROPIC_BASE_URL="{base}"\n'
                f'$env:ANTHROPIC_AUTH_TOKEN="{PLACEHOLDER_PASSWORD}"\n'
                f'$env:ANTHROPIC_MODEL="{model}"\nclaude'
            ),
            "openai": (
                f'curl "{openai_base}/chat/completions" -H "Authorization: Bearer {PLACEHOLDER_PASSWORD}" '
                f'-H "Content-Type: application/json" -d \'{{"model":"{model}","messages":[{{"role":"user","content":"你好"}}]}}\''
            ),
            "gemini": (
                f'curl "{base}/v1/models/{model}:generateContent" -H "x-goog-api-key: {PLACEHOLDER_PASSWORD}" '
                f'-H "Content-Type: application/json" -d \'{{"contents":[{{"role":"user","parts":[{{"text":"你好"}}]}}]}}\''
            ),
        }

    @staticmethod
    def _redact(text: object, secrets: Iterable[str] = ()) -> str:
        value = str(text or "")
        value = re.sub(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+(?:\s+[^\s,;]+)?)", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)([?&]key=)[^&#\s]+", r"\1[REDACTED]", value)
        for secret in secrets:
            if secret:
                value = value.replace(str(secret), "[REDACTED]")
        return value
