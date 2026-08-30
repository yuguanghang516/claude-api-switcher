"""Safe, read-only application update checks against GitHub Releases."""

from dataclasses import dataclass
import re
import posixpath
from urllib.parse import unquote, urlsplit

import requests

from .version import APP_VERSION


REPO_URL = "https://github.com/yuguanghang516/claude-api-switcher"
RELEASES_URL = f"{REPO_URL}/releases"
CHANGELOG_URL = f"{REPO_URL}/tree/main/docs/releases"
FEEDBACK_URL = f"{REPO_URL}/issues/new/choose"
LATEST_RELEASE_API = "https://api.github.com/repos/yuguanghang516/claude-api-switcher/releases/latest"


@dataclass(frozen=True)
class UpdateCheckResult:
    status: str
    current_version: str = APP_VERSION
    latest_version: str = ""
    release_url: str = RELEASES_URL
    message: str = ""


def _version_tuple(value: str):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", value.strip())
    return tuple(map(int, match.groups())) if match else None


def _safe_release_url(value: object) -> str:
    """仅允许打开本仓库的 HTTPS Release 页面。"""
    if not isinstance(value, str):
        return RELEASES_URL
    try:
        parsed = urlsplit(value.strip())
        path = posixpath.normpath(unquote(parsed.path)).rstrip("/").lower()
        releases_path = "/yuguanghang516/claude-api-switcher/releases"
        if (
            parsed.scheme.lower() == "https"
            and parsed.hostname
            and parsed.hostname.lower() == "github.com"
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and not parsed.query
            and not parsed.fragment
            and (path == releases_path or path.startswith(f"{releases_path}/"))
        ):
            return value.strip()
    except (TypeError, ValueError):
        pass
    return RELEASES_URL


def check_for_updates(timeout: float = 8.0) -> UpdateCheckResult:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Claude-API-Switcher/{APP_VERSION}",
    }
    try:
        response = requests.get(
            LATEST_RELEASE_API, headers=headers, timeout=timeout, allow_redirects=False
        )
    except requests.exceptions.Timeout:
        return UpdateCheckResult("network_error", message="检查超时，请稍后重试")
    except requests.exceptions.RequestException:
        return UpdateCheckResult("network_error", message="无法连接 GitHub，请检查网络或代理")

    if response.status_code == 404:
        return UpdateCheckResult("no_release", message="项目暂未发布 GitHub Release")
    if response.status_code == 403:
        return UpdateCheckResult("rate_limited", message="GitHub 请求受限，请稍后重试")
    if response.status_code != 200:
        return UpdateCheckResult(
            "server_error", message=f"GitHub 返回 HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError:
        return UpdateCheckResult("server_error", message="GitHub 返回内容无法解析")

    latest = str(payload.get("tag_name") or "").strip()
    release_url = _safe_release_url(payload.get("html_url"))
    current_tuple = _version_tuple(APP_VERSION)
    latest_tuple = _version_tuple(latest)
    if not latest_tuple or not current_tuple:
        return UpdateCheckResult(
            "server_error", latest_version=latest, release_url=release_url,
            message="Release 版本号格式不正确",
        )
    if latest_tuple > current_tuple:
        return UpdateCheckResult(
            "update_available", latest_version=latest.lstrip("vV"),
            release_url=release_url, message=f"发现新版本 V{latest.lstrip('vV')}",
        )
    return UpdateCheckResult(
        "up_to_date", latest_version=latest.lstrip("vV"), release_url=release_url,
        message="已是最新版本",
    )
