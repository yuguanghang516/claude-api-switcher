"""项目目录与 Claude 命令的安全自动识别。"""
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
import shutil
from typing import Any, Optional


@dataclass(frozen=True)
class DirectoryResolution:
    path: str
    source: str  # manual | recent | recorded | home


class ProjectDirectoryResolver:
    """从手动配置、Claude 最近项目和用户目录中选择可用 cwd。"""

    def __init__(self, home_dir: Optional[str] = None, claude_json: Optional[str] = None):
        self.home_dir = os.path.abspath(home_dir or os.path.expanduser("~"))
        self.claude_json = claude_json or os.path.join(self.home_dir, ".claude.json")

    def resolve(self, manual_path: str = "") -> Optional[DirectoryResolution]:
        manual = self._existing_directory(manual_path)
        if manual:
            return DirectoryResolution(manual, "manual")

        projects = self._load_projects()
        timed = [item for item in projects if item[1] is not None]
        if timed:
            timed.sort(key=lambda item: item[1], reverse=True)
            return DirectoryResolution(timed[0][0], "recent")
        if projects:
            return DirectoryResolution(projects[-1][0], "recorded")

        home = self._existing_directory(self.home_dir)
        return DirectoryResolution(home, "home") if home else None

    def _load_projects(self):
        try:
            with open(self.claude_json, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, ValueError, TypeError):
            return []
        if not isinstance(data, dict):
            return []
        projects = data.get("projects")
        if not isinstance(projects, dict):
            return []
        result = []
        for raw_path, metadata in projects.items():
            path = self._existing_directory(raw_path)
            if not path:
                continue
            timestamp = self._timestamp(metadata.get("lastStartTime") if isinstance(metadata, dict) else None)
            result.append((path, timestamp))
        return result

    @staticmethod
    def _timestamp(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            numeric = float(value)
            return numeric if math.isfinite(numeric) else None
        if isinstance(value, str) and value.strip():
            text = value.strip()
            try:
                numeric = float(text)
                return numeric if math.isfinite(numeric) else None
            except ValueError:
                try:
                    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
                except (ValueError, OSError, OverflowError):
                    return None
        return None

    @staticmethod
    def _existing_directory(path: str) -> str:
        if not isinstance(path, str) or not path.strip():
            return ""
        normalized = os.path.abspath(os.path.normpath(path.strip()))
        return normalized if os.path.isdir(normalized) else ""


class ClaudeCommandResolver:
    """返回可直接执行的 Claude 命令绝对路径。"""

    @staticmethod
    def resolve() -> str:
        for name in ("claude.cmd", "claude.exe", "claude"):
            path = shutil.which(name)
            if path and os.path.isfile(path):
                return os.path.abspath(path)

        home = os.path.expanduser("~")
        candidates = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "npm", "claude.cmd"))
        candidates.append(os.path.join(home, ".local", "bin", "claude.exe"))
        for path in candidates:
            if path and os.path.isfile(path):
                return os.path.abspath(path)
        return ""
