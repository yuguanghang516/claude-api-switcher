from app.client_source import classify_client_source
from app.db_manager import DatabaseManager


def test_client_source_classifier_is_coarse():
    assert classify_client_source({"User-Agent": "claude-cli/2"}) == "claude"
    assert classify_client_source({"User-Agent": "codex-cli/1"}) == "codex"
    assert classify_client_source({"X-Client-Source": "Codex Desktop"}) == "codex"
    assert classify_client_source({"User-Agent": "curl/8"}) == "other"


def test_provider_usage_excludes_codex_rows(tmp_path):
    db = DatabaseManager(str(tmp_path))
    common = {
        "provider": "local-api", "model": "model", "input_tokens": 10,
        "output_tokens": 5, "total_tokens": 15, "status": "success",
    }
    db.log_request({**common, "client_source": "claude"})
    db.log_request({**common, "client_source": "codex"})

    rows = db.get_usage_by_provider()
    assert rows[0]["total_requests"] == 1
    assert rows[0]["total_tokens"] == 15


def test_existing_database_gets_client_source_column(tmp_path):
    import sqlite3

    db_path = tmp_path / "gateway.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE request_logs (
            id INTEGER PRIMARY KEY, request_time INTEGER, model TEXT, provider TEXT,
            input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
            response_time_ms INTEGER, status TEXT, error TEXT, endpoint TEXT
        )
    """)
    conn.commit()
    conn.close()

    db = DatabaseManager(str(tmp_path))
    columns = {row[1] for row in db._get_conn().execute("PRAGMA table_info(request_logs)")}
    assert "client_source" in columns
