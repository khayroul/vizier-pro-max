"""Tests for dream-skill consolidator -- 4-phase memory consolidation."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from augments.dreamskill.consolidator import consolidate


@pytest.fixture()
def mock_log_db(tmp_path: Path) -> Path:
    """Create a mock prompt_log database."""
    db_path = tmp_path / "prompt_log.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY, session_id TEXT,
            timestamp TEXT, tool_name TEXT, tool_args TEXT, result TEXT
        )
    """)
    entries = [
        ("s1", "2026-04-01", "chat", "{}",
         "No, use light theme not dark."),
        ("s2", "2026-04-02", "chat", "{}",
         "I prefer 1080x1080 for Instagram."),
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


@pytest.fixture()
def memory_dir(tmp_path: Path) -> Path:
    """Create a memory directory with existing MEMORY.md."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text(
        "- [2026-03-30] Use dark theme for all designs."
        " (confidence: high)\n"
    )
    return mem_dir


class TestConsolidator:
    def test_consolidate_with_qwen_mock(
        self, mock_log_db: Path, memory_dir: Path, tmp_path: Path
    ) -> None:
        """Consolidator calls Qwen and updates MEMORY.md."""
        qwen_response = (
            "- [2026-04-01] Use light theme, not dark."
            " (Updated 2026-04-01, previously: dark theme) (confidence: high)\n"
            "- [2026-04-02] Instagram posts use 1080x1080. (confidence: high)\n"
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": qwen_response}

        target = "augments.dreamskill.consolidator.httpx.post"
        with patch(target, return_value=mock_resp):
            result = consolidate(
                db_path=mock_log_db,
                memory_dir=memory_dir,
            )

        assert result["status"] == "consolidated"
        memory_content = (memory_dir / "MEMORY.md").read_text()
        assert "light theme" in memory_content

    def test_consolidate_falls_back_on_ollama_error(
        self, mock_log_db: Path, memory_dir: Path
    ) -> None:
        """Falls back to rule-based when Ollama is unreachable."""
        with patch(
            "augments.dreamskill.consolidator.httpx.post",
            side_effect=ConnectionError("Connection refused"),
        ):
            result = consolidate(
                db_path=mock_log_db,
                memory_dir=memory_dir,
            )

        assert result["status"] in ("consolidated", "fallback")
        # MEMORY.md should still be updated (rule-based)
        assert (memory_dir / "MEMORY.md").exists()

    def test_consolidate_skips_if_recent(
        self, mock_log_db: Path, memory_dir: Path
    ) -> None:
        """Skips if .last-dream is recent (<24h)."""
        (memory_dir / ".last-dream").write_text(str(time.time()))

        result = consolidate(
            db_path=mock_log_db,
            memory_dir=memory_dir,
        )
        assert result["status"] == "skipped"
