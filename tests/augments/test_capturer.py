"""Tests for OpenSpace capturer -- pattern detection from structlog."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from augments.openspace.capturer import detect_repeating_chains


@pytest.fixture()
def mock_prompt_db(tmp_path: Path) -> Path:
    """Create a mock prompt_log database with repeating tool chains."""
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
    # Insert a repeating chain: fetch -> render -> screenshot (5+ times)
    for session in range(6):
        for step, tool in enumerate(
            ["httpx_fetch", "jinja2_render", "playwright_screenshot"]
        ):
            insert_sql = (
                "INSERT INTO prompt_log"
                " (session_id, timestamp, tool_name, tool_args, result)"
                " VALUES (?, ?, ?, ?, ?)"
            )
            conn.execute(
                insert_sql,
                (f"session_{session}", f"2026-04-0{session + 1}", tool, "{}", "ok"),
            )
    # Insert a non-repeating chain (only 2 occurrences)
    for session in range(2):
        rare_sql = (
            "INSERT INTO prompt_log"
            " (session_id, timestamp, tool_name, tool_args, result)"
            " VALUES (?, ?, ?, ?, ?)"
        )
        conn.execute(
            rare_sql,
            (f"rare_{session}", "2026-04-01", "pandas_analyze", "{}", "ok"),
        )
    conn.commit()
    conn.close()
    return db_path


class TestCapturer:
    def test_detect_repeating_chain(self, mock_prompt_db: Path) -> None:
        chains = detect_repeating_chains(db_path=mock_prompt_db, threshold=5)
        assert len(chains) >= 1
        # The fetch->render->screenshot chain should be detected
        chain_tools = [c["tools"] for c in chains]
        assert any(
            "httpx_fetch" in tools and "jinja2_render" in tools
            for tools in chain_tools
        )

    def test_ignore_below_threshold(self, mock_prompt_db: Path) -> None:
        chains = detect_repeating_chains(db_path=mock_prompt_db, threshold=10)
        assert len(chains) == 0

    def test_empty_database(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
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
        conn.close()
        chains = detect_repeating_chains(db_path=db_path, threshold=5)
        assert chains == []
