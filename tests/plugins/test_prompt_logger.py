"""Tests for prompt logger lifecycle hooks."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.prompt_logger import _ensure_table, post_llm_call, pre_llm_call


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary SQLite database path."""
    return tmp_path / "test_state.db"


@pytest.fixture(autouse=True)
def _patch_db(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch DB_PATH to use temp database and reset step counter."""
    import plugins.prompt_logger as pl

    monkeypatch.setattr("plugins.prompt_logger.DB_PATH", str(db_path))
    monkeypatch.setattr(pl, "_step_counter", {})
    _ensure_table(str(db_path))


class TestPreLLMCall:
    def test_inserts_log_entry(self, db_path: Path) -> None:
        messages = [{"role": "user", "content": "hello"}]
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-1")

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM prompt_log").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_increments_step_counter(self, db_path: Path) -> None:
        messages = [{"role": "user", "content": "hello"}]
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-1")
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-1")

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT step FROM prompt_log WHERE task_id = 'task-1' ORDER BY step"
        ).fetchall()
        conn.close()
        assert [r[0] for r in rows] == [1, 2]


class TestPostLLMCall:
    def test_updates_token_counts(self, db_path: Path) -> None:
        messages = [{"role": "user", "content": "hello"}]
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-2")
        post_llm_call(
            response=None,
            task_id="task-2",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT tokens_in, tokens_out FROM prompt_log WHERE task_id = 'task-2'"
        ).fetchone()
        conn.close()
        assert row == (100, 50)
