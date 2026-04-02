"""Tests for scripts.bridge.sync_hermes_sessions — Hermes state.db → training_sessions ETL."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def _create_hermes_db(db_path: Path) -> None:
    """Create a minimal Hermes state.db with sessions + messages tables."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            user_id TEXT,
            model TEXT,
            started_at REAL NOT NULL,
            ended_at REAL,
            end_reason TEXT,
            tool_call_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            title TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _create_training_db(db_path: Path) -> None:
    """Create the training_sessions table in prompt_log.db."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS training_sessions (
            session_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            input_message TEXT NOT NULL,
            task_type TEXT NOT NULL,
            toolset_chosen TEXT NOT NULL,
            pipeline_used TEXT NOT NULL,
            tool_calls TEXT NOT NULL,
            success INTEGER NOT NULL,
            synthetic INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_session(
    conn: sqlite3.Connection,
    session_id: str,
    source: str = "cli",
    started_at: float = 1743465600.0,
    ended_at: float | None = 1743465900.0,
    end_reason: str | None = "completed",
    tool_call_count: int = 3,
) -> None:
    conn.execute(
        "INSERT INTO sessions (id, source, started_at, ended_at, end_reason, tool_call_count)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, source, started_at, ended_at, end_reason, tool_call_count),
    )


def _insert_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str | None,
    tool_name: str | None = None,
    timestamp: float = 1743465601.0,
) -> None:
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_name, timestamp)"
        " VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, tool_name, timestamp),
    )


class TestSyncHermesSessions:
    """Test ETL from Hermes state.db to training_sessions."""

    def test_basic_sync(self, tmp_path: Path) -> None:
        """Single completed session with user message and tool calls syncs correctly."""
        hermes_db = tmp_path / "state.db"
        training_db = tmp_path / "prompt_log.db"

        _create_hermes_db(hermes_db)
        _create_training_db(training_db)

        conn = sqlite3.connect(str(hermes_db))
        _insert_session(conn, "sess-001", end_reason="completed")
        _insert_message(conn, "sess-001", "user", "Analyze sales data for Q1")
        _insert_message(conn, "sess-001", "assistant", None, tool_name="analyze_data")
        _insert_message(conn, "sess-001", "assistant", None, tool_name="render_chart")
        _insert_message(conn, "sess-001", "assistant", "Here are the results.")
        conn.commit()
        conn.close()

        from scripts.bridge.sync_hermes_sessions import sync_sessions

        count = sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)
        assert count == 1

        conn = sqlite3.connect(str(training_db))
        row = conn.execute(
            "SELECT session_id, input_message, task_type, toolset_chosen,"
            " success, synthetic FROM training_sessions WHERE session_id = ?",
            ("sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "sess-001"
        assert row[1] == "Analyze sales data for Q1"
        assert row[4] == 1  # success (completed)
        assert row[5] == 0  # synthetic = False

    def test_idempotent_skip(self, tmp_path: Path) -> None:
        """Running sync twice does not duplicate rows."""
        hermes_db = tmp_path / "state.db"
        training_db = tmp_path / "prompt_log.db"

        _create_hermes_db(hermes_db)
        _create_training_db(training_db)

        conn = sqlite3.connect(str(hermes_db))
        _insert_session(conn, "sess-002", end_reason="completed")
        _insert_message(conn, "sess-002", "user", "Generate a poster")
        conn.commit()
        conn.close()

        from scripts.bridge.sync_hermes_sessions import sync_sessions

        count1 = sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)
        count2 = sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)

        assert count1 == 1
        assert count2 == 0  # skipped because already synced

        conn = sqlite3.connect(str(training_db))
        total = conn.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0]
        conn.close()
        assert total == 1

    def test_failed_session_marks_success_zero(self, tmp_path: Path) -> None:
        """A session with end_reason != 'completed' gets success=0."""
        hermes_db = tmp_path / "state.db"
        training_db = tmp_path / "prompt_log.db"

        _create_hermes_db(hermes_db)
        _create_training_db(training_db)

        conn = sqlite3.connect(str(hermes_db))
        _insert_session(conn, "sess-003", end_reason="error")
        _insert_message(conn, "sess-003", "user", "Convert this PDF")
        conn.commit()
        conn.close()

        from scripts.bridge.sync_hermes_sessions import sync_sessions

        sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)

        conn = sqlite3.connect(str(training_db))
        row = conn.execute(
            "SELECT success FROM training_sessions WHERE session_id = ?",
            ("sess-003",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 0

    def test_no_user_message_skips_session(self, tmp_path: Path) -> None:
        """A session with no user messages is skipped."""
        hermes_db = tmp_path / "state.db"
        training_db = tmp_path / "prompt_log.db"

        _create_hermes_db(hermes_db)
        _create_training_db(training_db)

        conn = sqlite3.connect(str(hermes_db))
        _insert_session(conn, "sess-004", end_reason="completed")
        _insert_message(conn, "sess-004", "system", "You are a helpful assistant.")
        conn.commit()
        conn.close()

        from scripts.bridge.sync_hermes_sessions import sync_sessions

        count = sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)
        assert count == 0

    def test_tool_calls_extracted(self, tmp_path: Path) -> None:
        """Tool names from messages are collected into tool_calls JSON."""
        hermes_db = tmp_path / "state.db"
        training_db = tmp_path / "prompt_log.db"

        _create_hermes_db(hermes_db)
        _create_training_db(training_db)

        conn = sqlite3.connect(str(hermes_db))
        _insert_session(conn, "sess-005", end_reason="completed")
        _insert_message(conn, "sess-005", "user", "Merge these PDFs together")
        _insert_message(conn, "sess-005", "assistant", None, tool_name="merge_pdfs")
        _insert_message(conn, "sess-005", "assistant", None, tool_name="send_telegram")
        conn.commit()
        conn.close()

        from scripts.bridge.sync_hermes_sessions import sync_sessions

        sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)

        conn = sqlite3.connect(str(training_db))
        row = conn.execute(
            "SELECT tool_calls FROM training_sessions WHERE session_id = ?",
            ("sess-005",),
        ).fetchone()
        conn.close()

        assert row is not None
        tool_calls = json.loads(row[0])
        assert "merge_pdfs" in tool_calls
        assert "send_telegram" in tool_calls

    def test_multiple_sessions_synced(self, tmp_path: Path) -> None:
        """Multiple sessions are all synced in one call."""
        hermes_db = tmp_path / "state.db"
        training_db = tmp_path / "prompt_log.db"

        _create_hermes_db(hermes_db)
        _create_training_db(training_db)

        conn = sqlite3.connect(str(hermes_db))
        for i in range(5):
            sid = f"sess-multi-{i}"
            _insert_session(conn, sid, end_reason="completed")
            _insert_message(conn, sid, "user", f"Task number {i}")
        conn.commit()
        conn.close()

        from scripts.bridge.sync_hermes_sessions import sync_sessions

        count = sync_sessions(hermes_db_path=hermes_db, training_db_path=training_db)
        assert count == 5
