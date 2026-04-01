"""Prompt Logger — Hermes lifecycle hook plugin.

Captures the full prompt chain for every LLM call into SQLite.
This is a lifecycle hook (pre_llm_call / post_llm_call), NOT a tool.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")

_MAX_TRACKED_TASKS = 10_000
_step_counter: dict[str, int] = {}
_lock = threading.Lock()
_table_ensured = False


def _ensure_table(db_path: str | None = None) -> None:
    """Create the prompt_log table if it does not exist."""
    global _table_ensured  # noqa: PLW0603
    with _lock:
        if _table_ensured and db_path is None:
            return
        path = db_path or DB_PATH
        with sqlite3.connect(path) as conn:
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
                    tokens_out INTEGER DEFAULT 0,
                    deliverable_id TEXT
                )
            """)
        if db_path is None:
            _table_ensured = True


def pre_llm_call(
    messages: list[dict],  # type: ignore[type-arg]
    model: str,
    tools: list[dict] | None = None,  # type: ignore[type-arg]
    task_id: str | None = None,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook — fires before every LLM call."""
    try:
        _ensure_table()
        effective_task_id = task_id or "unknown"
        with _lock:
            if len(_step_counter) >= _MAX_TRACKED_TASKS:
                _step_counter.clear()
            _step_counter[effective_task_id] = (
                _step_counter.get(effective_task_id, 0) + 1
            )
            step = _step_counter[effective_task_id]

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO prompt_log
                   (task_id, step, model, messages_json, tools_json, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    effective_task_id,
                    step,
                    model or "unknown",
                    json.dumps(messages, ensure_ascii=False, default=str),
                    (
                        json.dumps(
                            tools,
                            ensure_ascii=False,
                            default=str,
                        )
                        if tools
                        else "[]"
                    ),
                    time.time(),
                ],
            )
    except (sqlite3.Error, OSError, ValueError) as exc:
        logger.warning("prompt_logger pre_llm_call failed (non-fatal): %s", exc)


def post_llm_call(
    response: object = None,
    task_id: str | None = None,
    usage: dict[str, int] | None = None,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook — fires after every LLM call. Updates token counts."""
    try:
        if task_id is None or usage is None:
            return

        with _lock:
            step = _step_counter.get(task_id, 0)

        with sqlite3.connect(DB_PATH) as conn:
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
    except (sqlite3.Error, OSError, ValueError) as exc:
        logger.warning("prompt_logger post_llm_call failed (non-fatal): %s", exc)
