"""Privacy-preserving usage summaries from local Claude Code session files."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional


TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _empty_stats() -> Dict[str, int]:
    return {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "content_tokens": 0,
        "cache_tokens": 0,
        "total_tokens": 0,
    }


class ClaudeUsageScanner:
    """Read only timing, model, message id and numeric usage fields from JSONL."""

    def __init__(self, projects_dir: Path | str | None = None, *,
                 max_files: int = 5000, max_total_bytes: int = 1_000_000_000,
                 max_line_bytes: int = 16_000_000) -> None:
        profile = Path(os.environ.get("USERPROFILE") or Path.home())
        self.projects_dir = Path(projects_dir) if projects_dir else profile / ".claude" / "projects"
        self.max_files = max(1, max_files)
        self.max_total_bytes = max(1, max_total_bytes)
        self.max_line_bytes = max(1024, max_line_bytes)

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _parse_time(value: object) -> Optional[datetime]:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
        except (ValueError, OSError):
            return None

    def _files(self) -> Iterable[Path]:
        root = self.projects_dir
        if not root.is_dir():
            return ()
        files = []
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            base = Path(directory)
            dirnames[:] = [name for name in dirnames if not (base / name).is_symlink()]
            for name in filenames:
                if not name.lower().endswith(".jsonl"):
                    continue
                path = base / name
                if path.is_symlink():
                    continue
                try:
                    resolved = path.resolve()
                    resolved.relative_to(root.resolve())
                    stat = resolved.stat()
                except (OSError, ValueError):
                    continue
                files.append((stat.st_mtime, stat.st_size, resolved))
        files.sort(key=lambda item: item[0], reverse=True)
        return tuple(item[2] for item in files[:self.max_files])

    @staticmethod
    def _add(stats: Dict[str, int], record: Dict[str, object]) -> None:
        stats["calls"] += 1
        total = 0
        for field in TOKEN_FIELDS:
            value = int(record[field])
            stats[field] += value
            total += value
        stats["content_tokens"] += int(record["input_tokens"]) + int(record["output_tokens"])
        stats["cache_tokens"] += (
            int(record["cache_creation_input_tokens"]) + int(record["cache_read_input_tokens"])
        )
        stats["total_tokens"] += total

    def scan(self, now: Optional[datetime] = None) -> Dict[str, object]:
        local_now = (now or datetime.now().astimezone()).astimezone()
        today_key = local_now.date().isoformat()
        month_key = local_now.strftime("%Y-%m")
        records: Dict[str, Dict[str, object]] = {}
        diagnostics = {
            "files_scanned": 0,
            "files_skipped": 0,
            "malformed_lines": 0,
            "oversized_lines": 0,
            "bytes_scanned": 0,
            "truncated": False,
        }

        for path in self._files():
            try:
                size = path.stat().st_size
            except OSError:
                diagnostics["files_skipped"] += 1
                continue
            if diagnostics["bytes_scanned"] + size > self.max_total_bytes:
                diagnostics["truncated"] = True
                break
            diagnostics["bytes_scanned"] += size
            diagnostics["files_scanned"] += 1
            try:
                with path.open("rb") as handle:
                    for line_number, raw_line in enumerate(handle, 1):
                        if len(raw_line) > self.max_line_bytes:
                            diagnostics["oversized_lines"] += 1
                            continue
                        try:
                            payload = json.loads(raw_line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            diagnostics["malformed_lines"] += 1
                            continue
                        if not isinstance(payload, dict) or payload.get("type") != "assistant":
                            continue
                        message = payload.get("message")
                        if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                            continue
                        timestamp = self._parse_time(payload.get("timestamp"))
                        model = str(message.get("model") or "未知模型").strip() or "未知模型"
                        record = {field: self._safe_int(message["usage"].get(field)) for field in TOKEN_FIELDS}
                        if not any(record.values()) or timestamp is None:
                            continue
                        record.update({"timestamp": timestamp, "model": model})
                        message_id = str(message.get("id") or payload.get("uuid") or "").strip()
                        key = message_id or f"{path}:{line_number}:{timestamp.isoformat()}"
                        previous = records.get(key)
                        if previous is None or sum(int(record[field]) for field in TOKEN_FIELDS) > sum(
                                int(previous[field]) for field in TOKEN_FIELDS):
                            records[key] = record
            except OSError:
                diagnostics["files_skipped"] += 1

        result = {
            "today": _empty_stats(),
            "month": _empty_stats(),
            "all_time": _empty_stats(),
            "models": [],
            "heatmap": [],
            "diagnostics": diagnostics,
        }
        heatmap_start = local_now.date() - timedelta(days=6)
        heatmap_hours = {
            (heatmap_start + timedelta(days=offset)).isoformat(): [0] * 24
            for offset in range(7)
        }
        model_stats: Dict[str, Dict[str, int]] = {}
        for record in records.values():
            timestamp = record["timestamp"]
            content_total = int(record["input_tokens"]) + int(record["output_tokens"])
            self._add(result["all_time"], record)
            if timestamp.strftime("%Y-%m") == month_key:
                self._add(result["month"], record)
                stats = model_stats.setdefault(str(record["model"]), _empty_stats())
                self._add(stats, record)
            if timestamp.date().isoformat() == today_key:
                self._add(result["today"], record)
            heatmap_row = heatmap_hours.get(timestamp.date().isoformat())
            if heatmap_row is not None:
                heatmap_row[timestamp.hour] += content_total

        result["models"] = [
            {"model": model, **stats}
            for model, stats in sorted(
                model_stats.items(), key=lambda item: item[1]["content_tokens"], reverse=True)
        ]
        result["heatmap"] = [
            {"date": day, "hours": hours}
            for day, hours in heatmap_hours.items()
        ]
        return result
