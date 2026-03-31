"""Tests for query_logs Hermes tool."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tools.query_logs import query_logs


@pytest.fixture()
def db_with_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp database with sample prompt log entries."""
    db_path = tmp_path / "test_state.db"
    monkeypatch.setattr("tools.query_logs.DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY, task_id TEXT, step INTEGER,
            model TEXT, messages_json TEXT, tools_json TEXT,
            timestamp REAL, tokens_in INTEGER, tokens_out INTEGER
        )
    """)
    conn.executemany(
        "INSERT INTO prompt_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "task-1", 1, "gpt-5.4-mini", "[]", "[]", 1000.0, 100, 50),
            (2, "task-1", 2, "gpt-5.4-mini", "[]", "[]", 1001.0, 200, 80),
            (3, "task-2", 1, "gpt-5.4-mini", "[]", "[]", 1002.0, 150, 60),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


class TestQueryLogs:
    def test_returns_last_n_entries(self, db_with_logs: Path) -> None:
        result = json.loads(query_logs({"last_n": 2}))
        assert len(result["entries"]) == 2

    def test_filters_by_task_id(self, db_with_logs: Path) -> None:
        result = json.loads(query_logs({"task_id": "task-1"}))
        assert len(result["entries"]) == 2
        assert all(e["task_id"] == "task-1" for e in result["entries"])

    def test_returns_token_summary(self, db_with_logs: Path) -> None:
        result = json.loads(query_logs({"task_id": "task-1", "summary": True}))
        assert result["total_tokens_in"] == 300
        assert result["total_tokens_out"] == 130

    def test_returns_error_on_missing_table(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "empty.db"
        # Create an empty database (no prompt_log table)
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.close()
        monkeypatch.setattr("tools.query_logs.DB_PATH", str(db_path))

        result = json.loads(query_logs({}))
        assert "error" in result
        assert "database" in result["error"].lower()

    def test_returns_error_on_nonexistent_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # SQLite will create the file on connect, then fail on query
        db_path = tmp_path / "nonexistent.db"
        monkeypatch.setattr("tools.query_logs.DB_PATH", str(db_path))

        result = json.loads(query_logs({}))
        assert "error" in result

    def test_default_last_n_returns_up_to_ten(
        self, db_with_logs: Path
    ) -> None:
        # Only 3 entries exist, default last_n=10 should return all 3
        result = json.loads(query_logs({}))
        assert len(result["entries"]) == 3

    def test_summary_without_task_id_returns_entries(self, db_with_logs: Path) -> None:
        # summary=True but no task_id — falls through to normal query
        result = json.loads(query_logs({"summary": True, "last_n": 2}))
        assert "entries" in result
        assert len(result["entries"]) == 2
