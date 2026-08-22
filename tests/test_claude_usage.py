import json
from datetime import datetime, timezone

from app.claude_usage import ClaudeUsageScanner


def _assistant(message_id, timestamp, model="LongCat-2.0", **usage):
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": model,
            "usage": usage,
            "content": [{"type": "text", "text": "private conversation"}],
        },
        "secret": "must never appear in summary",
    }


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_scanner_summarizes_without_retaining_content(tmp_path):
    session = tmp_path / "project" / "session.jsonl"
    _write_jsonl(session, [
        _assistant("m1", "2026-08-23T01:00:00Z", input_tokens=10, output_tokens=5,
                   cache_creation_input_tokens=3, cache_read_input_tokens=2),
        {"type": "user", "message": {"content": "ignore me"}},
    ])
    scanner = ClaudeUsageScanner(tmp_path)

    result = scanner.scan(datetime(2026, 8, 23, 12, tzinfo=timezone.utc))

    assert result["today"] == {
        "calls": 1, "input_tokens": 10, "output_tokens": 5,
        "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2,
        "content_tokens": 15, "cache_tokens": 5,
        "total_tokens": 20,
    }
    assert result["models"][0]["model"] == "LongCat-2.0"
    assert "private conversation" not in json.dumps(result)
    assert "secret" not in json.dumps(result)


def test_scanner_keeps_largest_stream_snapshot_per_message(tmp_path):
    _write_jsonl(tmp_path / "session.jsonl", [
        _assistant("same", "2026-08-23T01:00:00Z", input_tokens=0, output_tokens=1),
        _assistant("same", "2026-08-23T01:00:01Z", input_tokens=100, output_tokens=20),
        _assistant("same", "2026-08-23T01:00:02Z", input_tokens=100, output_tokens=20),
    ])
    result = ClaudeUsageScanner(tmp_path).scan(
        datetime(2026, 8, 23, 12, tzinfo=timezone.utc))
    assert result["today"]["calls"] == 1
    assert result["today"]["total_tokens"] == 120


def test_scanner_separates_today_month_and_all_time(tmp_path):
    _write_jsonl(tmp_path / "session.jsonl", [
        _assistant("today", "2026-08-23T01:00:00Z", input_tokens=10),
        _assistant("month", "2026-08-01T01:00:00Z", output_tokens=20),
        _assistant("old", "2026-07-31T01:00:00Z", input_tokens=30),
    ])
    result = ClaudeUsageScanner(tmp_path).scan(
        datetime(2026, 8, 23, 12, tzinfo=timezone.utc))
    assert result["today"]["calls"] == 1
    assert result["month"]["calls"] == 2
    assert result["all_time"]["calls"] == 3


def test_scanner_tolerates_malformed_and_oversized_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_bytes(
        b"not-json\n" + b"x" * 1500 + b"\n" +
        json.dumps(_assistant("ok", "2026-08-23T01:00:00Z", input_tokens=4)).encode() + b"\n"
    )
    result = ClaudeUsageScanner(tmp_path, max_line_bytes=1024).scan(
        datetime(2026, 8, 23, 12, tzinfo=timezone.utc))
    assert result["today"]["total_tokens"] == 4
    assert result["diagnostics"]["malformed_lines"] == 1
    assert result["diagnostics"]["oversized_lines"] == 1


def test_missing_directory_returns_empty_summary(tmp_path):
    result = ClaudeUsageScanner(tmp_path / "missing").scan()
    assert result["all_time"]["calls"] == 0
    assert result["diagnostics"]["files_scanned"] == 0
    assert len(result["heatmap"]) == 7
    assert all(len(row["hours"]) == 24 for row in result["heatmap"])


def test_scanner_builds_seven_day_hourly_heatmap(tmp_path):
    timestamp = "2026-08-23T01:00:00Z"
    _write_jsonl(tmp_path / "session.jsonl", [
        _assistant("heat", timestamp, input_tokens=100, output_tokens=20),
    ])
    now = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)

    result = ClaudeUsageScanner(tmp_path).scan(now)

    parsed = ClaudeUsageScanner._parse_time(timestamp)
    row = next(item for item in result["heatmap"]
               if item["date"] == parsed.date().isoformat())
    assert row["hours"][parsed.hour] == 120
    assert sum(sum(item["hours"]) for item in result["heatmap"]) == 120


def test_heatmap_excludes_cache_tokens_but_summary_keeps_them(tmp_path):
    timestamp = "2026-08-23T01:00:00Z"
    _write_jsonl(tmp_path / "session.jsonl", [
        _assistant("cache", timestamp, input_tokens=10, output_tokens=5,
                   cache_creation_input_tokens=20, cache_read_input_tokens=1000),
    ])
    result = ClaudeUsageScanner(tmp_path).scan(
        datetime(2026, 8, 23, 12, tzinfo=timezone.utc))

    assert result["today"]["content_tokens"] == 15
    assert result["today"]["cache_tokens"] == 1020
    assert sum(sum(item["hours"]) for item in result["heatmap"]) == 15
