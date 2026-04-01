"""Tests for dream-skill signal extraction from structlog."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from augments.dreamskill.signals import extract_signals


@pytest.fixture()
def mock_log_db(tmp_path: Path) -> Path:
    """Create a mock prompt_log database with patterns."""
    db_path = tmp_path / "prompt_log.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            timestamp TEXT,
            tool_name TEXT,
            tool_args TEXT,
            result TEXT
        )
    """)
    # Insert entries with correction/preference patterns
    entries = [
        ("s1", "2026-04-01", "chat", "{}",
         "No, don't use dark theme. Use light theme instead."),
        ("s1", "2026-04-01", "chat", "{}",
         "I prefer Malay captions for Instagram posts."),
        ("s2", "2026-04-02", "chat", "{}",
         "Always use 1080x1080 for social posts."),
        ("s3", "2026-04-03", "chat", "{}",
         "The font should be Montserrat, not Arial."),
        ("s4", "2026-04-04", "chat", "{}",
         "Just a regular status update, nothing special."),
    ]
    insert_sql = (
        "INSERT INTO prompt_log"
        " (session_id, timestamp, tool_name, tool_args, result)"
        " VALUES (?, ?, ?, ?, ?)"
    )
    for entry in entries:
        conn.execute(insert_sql, entry)
    conn.commit()
    conn.close()
    return db_path


class TestSignals:
    def test_extract_signals_finds_patterns(self, mock_log_db: Path) -> None:
        signals = extract_signals(db_path=mock_log_db)
        assert len(signals) >= 2  # Should find corrections/preferences

    def test_signal_has_required_fields(self, mock_log_db: Path) -> None:
        signals = extract_signals(db_path=mock_log_db)
        if signals:
            signal = signals[0]
            assert "fact" in signal
            assert "date" in signal
            assert "confidence" in signal

    def test_empty_database(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE prompt_log (
                id INTEGER PRIMARY KEY, session_id TEXT,
                timestamp TEXT, tool_name TEXT, tool_args TEXT, result TEXT
            )
        """)
        conn.close()
        signals = extract_signals(db_path=db_path)
        assert signals == []
