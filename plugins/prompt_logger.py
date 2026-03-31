"""Prompt Logger — Hermes lifecycle hook plugin.

Captures the full prompt chain for every LLM call into SQLite.
This is a lifecycle hook (pre_llm_call / post_llm_call), NOT a tool.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")
_step_counter: dict[str, int] = {}


def _ensure_table(db_path: str | None = None) -> None:
    """Create the prompt_log table if it does not exist."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            step INTEGER,
            model TEXT,
            messages_json TEXT,
            tools_json TEXT,
            timestamp REAL,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def pre_llm_call(
    messages: list[dict],  # type: ignore[type-arg]
    model: str,
    tools: list[dict] | None = None,  # type: ignore[type-arg]
    task_id: str | None = None,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook — fires before every LLM call."""
    effective_task_id = task_id or "unknown"
    _step_counter[effective_task_id] = _step_counter.get(effective_task_id, 0) + 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO prompt_log
           (task_id, step, model, messages_json, tools_json, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            effective_task_id,
            _step_counter[effective_task_id],
            model or "unknown",
            json.dumps(messages, ensure_ascii=False, default=str),
            json.dumps(tools, ensure_ascii=False, default=str) if tools else "[]",
            time.time(),
        ],
    )
    conn.commit()
    conn.close()


def post_llm_call(
    response: object = None,
    task_id: str | None = None,
    usage: dict[str, int] | None = None,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook — fires after every LLM call. Updates token counts."""
    if task_id is None or usage is None:
        return

    step = _step_counter.get(task_id, 0)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """UPDATE prompt_log SET tokens_in = ?, tokens_out = ?
           WHERE task_id = ? AND step = ?""",
        [
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            task_id,
            step,
        ],
    )
    conn.commit()
    conn.close()
