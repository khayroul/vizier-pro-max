"""Query prompt logger traces — model-callable Hermes tool."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")


def query_logs(args: dict[str, Any], **kw: Any) -> str:
    """Query prompt log entries.

    Args:
        args: Dict with optional keys: last_n (int), task_id (str), summary (bool).
        **kw: Ignored extra keyword arguments.

    Returns:
        JSON string with entries list or token summary.
    """
    last_n = max(1, min(int(args.get("last_n", 10)), 1000))
    task_id = args.get("task_id")
    summary = args.get("summary", False)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            if summary and task_id:
                row = conn.execute(
                    """SELECT SUM(tokens_in) as total_in, SUM(tokens_out) as total_out,
                              COUNT(*) as call_count
                       FROM prompt_log WHERE task_id = ?""",
                    [task_id],
                ).fetchone()
                return json.dumps({
                    "task_id": task_id,
                    "total_tokens_in": row["total_in"] or 0,
                    "total_tokens_out": row["total_out"] or 0,
                    "call_count": row["call_count"],
                })

            if task_id:
                rows = conn.execute(
                    """SELECT task_id, step, model, tokens_in, tokens_out, timestamp
                       FROM prompt_log WHERE task_id = ? ORDER BY step""",
                    [task_id],
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT task_id, step, model, tokens_in, tokens_out, timestamp
                       FROM prompt_log ORDER BY id DESC LIMIT ?""",
                    [last_n],
                ).fetchall()

            entries = [dict(row) for row in rows]
            return json.dumps({"entries": entries})

    except sqlite3.OperationalError as exc:
        return json.dumps({"error": f"Database error: {exc}"})


def register_query_logs_tool() -> None:
    """Register query_logs as a Hermes tool in the vizier-core toolset."""
    try:
        from tools.registry import registry  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("Hermes registry not available — query_logs not registered")
        return

    registry.register(
        name="query_logs",
        toolset="vizier-core",
        schema={
            "type": "object",
            "properties": {
                "last_n": {
                    "type": "integer",
                    "description": "Return the last N log entries (default 10)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Filter by specific task ID",
                },
                "summary": {
                    "type": "boolean",
                    "description": "Return token totals instead of entries",
                },
            },
            "required": [],
        },
        handler=query_logs,
        check_fn=lambda: True,
        description=(
            "Inspect prompt logger traces: view LLM call chains, token usage per task"
        ),
    )
