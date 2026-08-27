"""Safe lifecycle and connectivity management for the optional gcli2api service."""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlparse

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:7861"
REPO_URL = "https://github.com/su-kaka/gcli2api.git"
WINGET_PACKAGES: Tuple[Tuple[str, str], ...] = (
    ("Git.Git", "git"),
    ("astral-sh.uv", "uv"),
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
PLACEHOLDER_PASSWORD = "YOUR_GCLI2API_PASSWORD"
MODE_ANTIGRAVITY = "antigravity"
MODE_GEMINI_CLI = "geminicli"
SUPPORTED_MODES = (MODE_ANTIGRAVITY, MODE_GEMINI_CLI)
MAX_IMPORT_FILES = 20
MAX_IMPORT_FILE_BYTES = 2 * 1024 * 1024
MAX_IMPORT_TOTAL_BYTES = 10 * 1024 * 1024


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
    mode: str = MODE_ANTIGRAVITY


@dataclass(frozen=True)
class GcliCredentialImportResult:
    ok: bool
    uploaded_count: int = 0
    total_count: int = 0
    message: str = ""
    errors: Tuple[str, ...] = ()


@dataclass(frozen=True)
class GcliModelQuota:
    model: str
    remaining_percent: float
    reset_time: str = ""
    reset_time_raw: str = ""
    credential_count: int = 1


@dataclass(frozen=True)
class GcliQuotaSnapshot:
    ok: bool
    models: Tuple[GcliModelQuota, ...] = ()
    credential_count: int = 0
    message: str = ""
    fetched_at: int = 0


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
        return self.models_url_for(MODE_GEMINI_CLI)

    @staticmethod
    def normalize_mode(mode: str) -> str:
        return mode if mode in SUPPORTED_MODES else MODE_ANTIGRAVITY

    def models_url_for(self, mode: str) -> str:
        mode = self.normalize_mode(mode)
        prefix = "/antigravity" if mode == MODE_ANTIGRAVITY else ""
        return f"{self.base_url}{prefix}/v1/models"

    def claude_base_url(self, mode: str) -> str:
        return (f"{self.base_url}/antigravity"
                if self.normalize_mode(mode) == MODE_ANTIGRAVITY else self.base_url)

    def gateway_base_url(self, mode: str) -> str:
        return f"{self.claude_base_url(mode)}/v1"

    @classmethod
    def auth_mode_for(cls, mode: str) -> str:
        return "x-api-key" if cls.normalize_mode(mode) == MODE_ANTIGRAVITY else "bearer"

    @classmethod
    def provider_name_for(cls, mode: str) -> str:
        return ("Gemini Antigravity (gcli2api)"
                if cls.normalize_mode(mode) == MODE_ANTIGRAVITY
                else "Gemini CLI Enterprise (gcli2api)")

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

    FEATURE_MODEL_PREFIXES = ("假流式/", "流式抗截断/")

    @classmethod
    def normalize_model_name(cls, model: str) -> str:
        """Return the real upstream model id instead of a gcli transport alias."""
        name = str(model or "").strip()
        changed = True
        while changed and name:
            changed = False
            for prefix in cls.FEATURE_MODEL_PREFIXES:
                if name.startswith(prefix):
                    name = name[len(prefix):].strip()
                    changed = True
        return name

    @classmethod
    def is_claude_text_model(cls, model: str) -> bool:
        """Hide gcli2api internal/image/agent entries from Claude-facing choices."""
        name = cls.normalize_model_name(model).lower()
        if not name:
            return False
        if any(marker in name for marker in ("image", "tab_", "chat_", "-agent", "_agent")):
            return False
        return any(family in name for family in ("gemini", "claude", "gpt-oss"))

    @staticmethod
    def model_priority_key(model: str) -> tuple:
        """Order stronger Claude-facing models first while keeping a stable fallback."""
        name = str(model or "").lower()
        if "claude" in name:
            family = 0
            tier = 0 if "opus" in name else (1 if "sonnet" in name else 2)
        elif "gpt-oss" in name or "gpt" in name:
            family = 1
            tier = 0 if any(size in name for size in ("120b", "200b", "405b")) else 1
        elif "gemini" in name:
            family = 2
            if "pro" in name:
                tier = 0
            elif "thinking" in name or "high" in name:
                tier = 1
            elif "flash" in name and not any(word in name for word in ("lite", "low", "extra-low")):
                tier = 2
            else:
                tier = 3
        else:
            family, tier = 3, 9
        thinking_penalty = 0 if "thinking" in name else 1
        return family, tier, thinking_penalty, name

    @classmethod
    def clean_claude_models(cls, models: Sequence[str]) -> Tuple[str, ...]:
        """Canonicalize aliases, remove non-text entries, de-duplicate and rank models."""
        clean = []
        seen = set()
        for value in models:
            model = cls.normalize_model_name(value)
            key = model.lower()
            if cls.is_claude_text_model(model) and key not in seen:
                clean.append(model)
                seen.add(key)
        return tuple(sorted(clean, key=cls.model_priority_key))

    def _status(self, **changes) -> Gcli2ApiStatus:
        base = {
            "base_url": self.base_url,
            "install_dir": self.install_dir,
            "installed": (self.install_dir / "web.py").is_file(),
            "version": self._version(),
        }
        base.update(changes)
        return Gcli2ApiStatus(**base)

    @staticmethod
    def _safe_response_detail(response: requests.Response) -> str:
        """Return a bounded server error without echoing credential payloads."""
        try:
            payload = response.json()
        except (ValueError, TypeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        detail = payload.get("detail") or payload.get("error") or payload.get("message") or ""
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("type") or ""
        text = str(detail).replace("\r", " ").replace("\n", " ").strip()
        sensitive_markers = ("access_token", "refresh_token", "authorization", "bearer ", "token=")
        if any(marker in text.lower() for marker in sensitive_markers):
            return "服务返回了包含敏感字段的错误，内容已隐藏"
        return text[:180]

    def import_credentials(self, paths: Sequence[Path | str], panel_password: str,
                           mode: str = MODE_ANTIGRAVITY) -> GcliCredentialImportResult:
        """Validate and upload credential JSON files through gcli2api's panel API."""
        mode = self.normalize_mode(mode)
        if mode != MODE_ANTIGRAVITY:
            return GcliCredentialImportResult(False, message="凭证导入仅支持 Antigravity 模式")
        if not panel_password:
            return GcliCredentialImportResult(False, message="请先填写本地 API 密码")
        selected = tuple(Path(path) for path in paths)
        if not selected:
            return GcliCredentialImportResult(False, message="没有选择 JSON 文件")
        if len(selected) > MAX_IMPORT_FILES:
            return GcliCredentialImportResult(
                False, total_count=len(selected), message=f"一次最多导入 {MAX_IMPORT_FILES} 个 JSON 文件")

        files = []
        errors: List[str] = []
        total_bytes = 0
        for path in selected:
            safe_name = path.name
            if path.suffix.lower() != ".json":
                errors.append(f"{safe_name}：只支持 .json 文件")
                continue
            try:
                size = path.stat().st_size
            except OSError:
                errors.append(f"{safe_name}：无法读取文件")
                continue
            if size <= 0:
                errors.append(f"{safe_name}：文件为空")
                continue
            if size > MAX_IMPORT_FILE_BYTES:
                errors.append(f"{safe_name}：超过 2 MiB")
                continue
            total_bytes += size
            if total_bytes > MAX_IMPORT_TOTAL_BYTES:
                errors.append("所选文件总大小超过 10 MiB")
                break
            try:
                content = path.read_bytes()
                payload = json.loads(content.decode("utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                errors.append(f"{safe_name}：不是有效的 UTF-8 JSON")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{safe_name}：JSON 顶层必须是对象")
                continue
            files.append(("files", (safe_name, content, "application/json")))

        if errors or not files:
            message = "导入前检查未通过" if errors else "没有可导入的 JSON 文件"
            return GcliCredentialImportResult(
                False, total_count=len(selected), message=message, errors=tuple(errors))

        headers = {"Authorization": f"Bearer {panel_password}", "Accept": "application/json"}
        try:
            response = requests.post(
                f"{self.base_url}/creds/upload", headers=headers,
                params={"mode": MODE_ANTIGRAVITY}, files=files,
                timeout=max(self.request_timeout, 60), allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            return GcliCredentialImportResult(
                False, total_count=len(selected), message="凭证导入超时；请检查服务和文件大小")
        except requests.exceptions.ConnectionError:
            return GcliCredentialImportResult(
                False, total_count=len(selected), message="无法连接 gcli2api；请先启动服务")
        except requests.exceptions.RequestException:
            return GcliCredentialImportResult(
                False, total_count=len(selected), message="凭证导入请求失败；敏感内容未记录")

        if 300 <= response.status_code < 400:
            return GcliCredentialImportResult(
                False, total_count=len(selected), message="服务返回重定向；为保护凭证已停止")
        if response.status_code in {401, 403}:
            return GcliCredentialImportResult(
                False, total_count=len(selected), message="面板密码不匹配；请填写服务启动时的 PANEL_PASSWORD")
        if response.status_code != 200:
            detail = self._safe_response_detail(response)
            suffix = f"：{detail}" if detail else ""
            return GcliCredentialImportResult(
                False, total_count=len(selected),
                message=f"gcli2api 拒绝导入（HTTP {response.status_code}）{suffix}")
        try:
            payload = response.json()
            uploaded = int(payload.get("uploaded_count", 0)) if isinstance(payload, dict) else 0
            results = payload.get("results", []) if isinstance(payload, dict) else []
        except (ValueError, TypeError):
            return GcliCredentialImportResult(
                False, total_count=len(selected), message="导入接口返回了无效数据")
        result_errors = tuple(
            f"{str(item.get('filename') or '文件')}：{str(item.get('message') or '处理失败')[:120]}"
            for item in results
            if isinstance(item, dict) and item.get("status") != "success"
        )
        ok = uploaded > 0 and not result_errors
        return GcliCredentialImportResult(
            ok, uploaded_count=uploaded, total_count=len(selected),
            message=f"已导入 {uploaded}/{len(selected)} 个 Antigravity 凭证",
            errors=result_errors,
        )

    def get_model_quotas(self, panel_password: str,
                         mode: str = MODE_ANTIGRAVITY) -> GcliQuotaSnapshot:
        """Read per-model quota snapshots without treating them as live availability."""
        mode = self.normalize_mode(mode)
        now = int(time.time())
        if mode != MODE_ANTIGRAVITY:
            return GcliQuotaSnapshot(False, message="逐模型额度仅支持 Antigravity 模式", fetched_at=now)
        if not panel_password:
            return GcliQuotaSnapshot(False, message="请先填写本地 API 密码", fetched_at=now)
        headers = {"Authorization": f"Bearer {panel_password}", "Accept": "application/json"}
        try:
            status_response = requests.get(
                f"{self.base_url}/creds/status", headers=headers,
                params={"offset": 0, "limit": 100, "status_filter": "enabled", "mode": mode},
                timeout=max(self.request_timeout, 15), allow_redirects=False,
            )
            if status_response.status_code in {401, 403}:
                return GcliQuotaSnapshot(False, message="面板密码不匹配", fetched_at=now)
            if status_response.status_code != 200:
                return GcliQuotaSnapshot(
                    False, message=f"凭证列表返回 HTTP {status_response.status_code}", fetched_at=now)
            payload = status_response.json()
            items = payload.get("items", []) if isinstance(payload, dict) else []
            filenames = [
                str(item.get("filename") or "") for item in items
                if isinstance(item, dict) and not item.get("disabled")
                and str(item.get("filename") or "").lower().endswith(".json")
            ]
            aggregate: Dict[str, Dict[str, object]] = {}
            for filename in filenames[:100]:
                quota_response = requests.get(
                    f"{self.base_url}/creds/quota/{quote(filename, safe='')}",
                    headers=headers, params={"mode": mode},
                    timeout=max(self.request_timeout, 30), allow_redirects=False,
                )
                if quota_response.status_code != 200:
                    continue
                quota_payload = quota_response.json()
                models = quota_payload.get("models", {}) if isinstance(quota_payload, dict) else {}
                if not isinstance(models, dict):
                    continue
                for model, info in models.items():
                    if not isinstance(info, dict) or not str(model).strip():
                        continue
                    try:
                        remaining = max(0.0, min(1.0, float(info.get("remaining"))))
                    except (TypeError, ValueError):
                        continue
                    entry = aggregate.setdefault(str(model), {
                        "remaining": remaining, "reset": "", "reset_raw": "", "count": 0,
                    })
                    entry["count"] = int(entry["count"]) + 1
                    if remaining >= float(entry["remaining"]):
                        entry["remaining"] = remaining
                        entry["reset"] = str(info.get("resetTime") or "")
                        entry["reset_raw"] = str(info.get("resetTimeRaw") or "")
        except requests.exceptions.Timeout:
            return GcliQuotaSnapshot(False, message="额度查询超时", fetched_at=now)
        except requests.exceptions.ConnectionError:
            return GcliQuotaSnapshot(False, message="无法连接 gcli2api；请先启动服务", fetched_at=now)
        except (requests.exceptions.RequestException, ValueError, TypeError):
            return GcliQuotaSnapshot(False, message="无法读取额度数据", fetched_at=now)

        models = tuple(sorted((
            GcliModelQuota(
                model=model, remaining_percent=float(info["remaining"]) * 100,
                reset_time=str(info["reset"]), reset_time_raw=str(info["reset_raw"]),
                credential_count=int(info["count"]),
            ) for model, info in aggregate.items()
        ), key=lambda item: (-item.remaining_percent, item.model.lower())))
        if not models:
            return GcliQuotaSnapshot(
                False, credential_count=len(filenames), message="没有可用的 Antigravity 额度数据",
                fetched_at=now)
        return GcliQuotaSnapshot(
            True, models=models, credential_count=len(filenames),
            message=f"{len(filenames)} 个凭证 · {len(models)} 个模型", fetched_at=now)

    def _antigravity_quota_models(self, api_password: str) -> Tuple[str, ...]:
        """Use gcli2api's authenticated quota API when its model-list call is empty."""
        snapshot = self.get_model_quotas(api_password, MODE_ANTIGRAVITY)
        return self.clean_claude_models(
            tuple(item.model for item in snapshot.models)
        ) if snapshot.ok else ()

    def detect(self, api_password: str = "", mode: str = MODE_ANTIGRAVITY) -> Gcli2ApiStatus:
        """Probe the service without following credential-bearing redirects."""

        mode = self.normalize_mode(mode)
        if self.is_local:
            self.refresh_install_dir()
        headers = {"Accept": "application/json"}
        if api_password:
            headers["Authorization"] = f"Bearer {api_password}"
        try:
            response = requests.get(
                self.models_url_for(mode), headers=headers, timeout=self.request_timeout,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            return self._status(state="error", error_code="timeout", mode=mode,
                                message="连接超时；请检查代理、防火墙和服务日志")
        except requests.exceptions.ConnectionError as exc:
            detail = str(exc).lower()
            if any(marker in detail for marker in ("getaddrinfo", "name resolution", "enotfound")):
                return self._status(state="error", error_code="dns", mode=mode,
                                    message="找不到服务器；请检查地址、网络或 DNS")
            if (self.install_dir / "web.py").is_file() and self.is_local:
                return self._status(state="stopped", error_code="connection_refused", mode=mode,
                                    message="gcli2api 已安装，但服务未启动")
            return self._status(state="not_installed", error_code="connection_refused", mode=mode,
                                message="未检测到 gcli2api 服务")
        except requests.exceptions.RequestException:
            return self._status(state="error", error_code="request_error", mode=mode,
                                message="请求异常；凭据未泄露")

        status = response.status_code
        if 300 <= status < 400:
            return self._status(state="error", running=True, error_code="redirect", mode=mode,
                                message="服务返回重定向；为保护密码已停止")
        if status == 401:
            return self._status(state="auth_required", running=True, error_code="auth_failed", mode=mode,
                                message="本地 API 密码错误或尚未填写；请填写服务启动时的 API_PASSWORD")
        if status == 403:
            # gcli2api 的模型列表端点在本地 API_PASSWORD 不匹配时返回 403。
            # Google 上游的 403 只会在实际消息请求阶段出现。
            return self._status(state="auth_required", running=True, error_code="auth_failed", mode=mode,
                                message="本地 API 密码不匹配；请填写服务启动时的 API_PASSWORD")
        if status == 404:
            endpoint = "/antigravity/v1/models" if mode == MODE_ANTIGRAVITY else "/v1/models"
            return self._status(state="error", running=True, error_code="not_found", mode=mode,
                                message=f"当前 gcli2api 不支持 {endpoint}；请更新 gcli2api")
        if status == 429:
            return self._status(state="error", running=True, error_code="rate_limited", mode=mode,
                                message="凭据额度不足或请求受限；请到管理面板检查凭据")
        if status >= 500:
            return self._status(state="error", running=True, error_code="server_error", mode=mode,
                                message=f"gcli2api 服务暂时不可用（HTTP {status}）")
        if status != 200:
            return self._status(state="error", running=True, error_code="http_error", mode=mode,
                                message=f"检测失败（HTTP {status}）")
        try:
            models = self._extract_models(response.json())
        except ValueError:
            return self._status(state="error", running=True, error_code="invalid_json", mode=mode,
                                message="模型接口返回了无效 JSON")
        if mode == MODE_ANTIGRAVITY:
            models = self.clean_claude_models(models)
        if not models and mode == MODE_ANTIGRAVITY:
            models = self._antigravity_quota_models(api_password)
        if not models:
            auth_name = "Antigravity认证并确认 AG 凭证正常" if mode == MODE_ANTIGRAVITY else "企业 Gemini CLI OAuth"
            return self._status(state="oauth_required", running=True, error_code="no_models", mode=mode,
                                message=f"服务已运行，但当前模式没有可用模型；请在面板完成{auth_name}")
        return self._status(state="ready", running=True, ready=True, models=models, mode=mode,
                            message=f"可以调用 · {len(models)} 个模型")

    @classmethod
    def select_models(cls, models: Sequence[str]) -> Tuple[str, str]:
        clean = list(cls.clean_claude_models(models))
        primary = clean[0] if clean else "gemini-2.5-pro"
        fast = next((model for model in clean if any(
            marker in model.lower() for marker in ("flash", "haiku", "lite")
        )), primary)
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

    def start_and_wait(self, api_password: str = "", panel_password: str = "",
                       mode: str = MODE_ANTIGRAVITY,
                       timeout: float = 15.0, poll_interval: float = 0.4
                       ) -> Tuple[bool, str, Gcli2ApiStatus]:
        """Start a local service and wait until its HTTP endpoint is observable.

        Process creation alone is not treated as success. Existing services are
        detected before spawning so an occupied port cannot produce a duplicate
        instance or a misleading success message.
        """

        mode = self.normalize_mode(mode)
        status = self.detect(api_password, mode)
        if status.running:
            if status.ready:
                return True, "gcli2api 服务已经启动并可以调用", status
            if status.state == "oauth_required":
                return True, "gcli2api 服务已经启动，下一步请完成 Google OAuth", status
            if status.state == "auth_required":
                return False, (
                    "检测到 gcli2api 已在运行，但当前 API 密码不匹配；"
                    "请填写该服务启动时设置的 API_PASSWORD，然后点击“检测服务”"
                ), status
            return False, f"gcli2api 已在运行，但尚不可调用：{status.message}", status

        ok, start_message = self.start(api_password, panel_password)
        if not ok:
            return False, start_message, status

        deadline = time.monotonic() + max(0.0, timeout)
        last_status = status
        while True:
            last_status = self.detect(api_password, mode)
            if last_status.running:
                if last_status.ready:
                    return True, "gcli2api 服务已启动并可以调用", last_status
                if last_status.state == "oauth_required":
                    return True, "gcli2api 服务已启动，下一步请完成 Google OAuth", last_status
                if last_status.state == "auth_required":
                    return False, (
                        "gcli2api 服务已启动，但 API 密码校验失败；"
                        "请确认输入的密码与 API_PASSWORD 一致"
                    ), last_status
                return False, f"gcli2api 服务已启动，但尚不可调用：{last_status.message}", last_status

            process = self._managed_process
            if process is not None:
                return_code = process.poll()
                if return_code is not None:
                    self._managed_process = None
                    self._managed_executable = ""
                    return False, (
                        f"gcli2api 进程启动后立即退出（退出码 {return_code}）；"
                        "请检查端口 7861 是否被占用，或在终端运行 web.py 查看错误"
                    ), last_status

            if time.monotonic() >= deadline:
                return False, (
                    f"gcli2api 进程已创建，但 {timeout:g} 秒内服务未响应；"
                    "请检查端口 7861、防火墙，并在终端运行 web.py 查看错误"
                ), last_status
            time.sleep(max(0.0, poll_interval))

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

    def generate_examples(self, model: str = "gemini-2.5-pro",
                          mode: str = MODE_ANTIGRAVITY) -> Dict[str, str]:
        mode = self.normalize_mode(mode)
        base = self.claude_base_url(mode)
        openai_base = self.gateway_base_url(mode)
        credential_env = ("ANTHROPIC_API_KEY" if self.auth_mode_for(mode) == "x-api-key"
                          else "ANTHROPIC_AUTH_TOKEN")
        return {
            "anthropic": (
                f'$env:ANTHROPIC_BASE_URL="{base}"\n'
                f'$env:{credential_env}="{PLACEHOLDER_PASSWORD}"\n'
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
