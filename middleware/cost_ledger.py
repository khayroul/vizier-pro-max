"""Cost Ledger — Hermes lifecycle hook capturing per-call cost data.

Uses ContextVar for per-call correlation (thread/async safe).
Reads deliverable_id from deliverable_context.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from middleware.deliverable_context import get_client_id, get_deliverable_id

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")

_call_rowid: ContextVar[int | None] = ContextVar("cost_ledger_rowid", default=None)
_call_start: ContextVar[float] = ContextVar("cost_ledger_start", default=0.0)

_tables_initialized = False


def _ensure_tables() -> None:
    """Lazily create cost_ledger tables if needed."""
    global _tables_initialized  # noqa: PLW0603
    if _tables_initialized:
        return

    migration = Path(__file__).parent.parent / "migrations" / "001_cost_ledger.sql"
    if not migration.exists():
        logger.warning("Migration file not found: %s", migration)
        _tables_initialized = True
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(migration.read_text())
    except sqlite3.OperationalError as exc:
        err_msg = str(exc).lower()
        if "duplicate column" in err_msg or "already exists" in err_msg:
            pass
        else:
            logger.warning("Migration error (non-fatal): %s", exc)
    conn.commit()
    conn.close()
    _tables_initialized = True


def pre_llm_call(
    messages: list[dict[str, Any]],
    model: str,
    step_name: str | None = None,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
    **kwargs: object,
) -> None:
    """Lifecycle hook — fires before every LLM call."""
    _ensure_tables()
    _call_start.set(time.monotonic())

    deliverable_id = get_deliverable_id()
    client_id = get_client_id()
    prompt_text = json.dumps(messages, ensure_ascii=False, default=str)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, pipeline_name, step_name,
            pipeline_version, model, prompt_text, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [deliverable_id, client_id, pipeline_name, step_name,
         pipeline_version, model or "unknown", prompt_text, time.time()],
    )
    _call_rowid.set(cursor.lastrowid)
    conn.commit()
    conn.close()


def post_llm_call(
    response_text: str | None = None,
    usage: dict[str, int] | None = None,
    **kwargs: object,
) -> None:
    """Lifecycle hook — fires after every LLM call."""
    rowid = _call_rowid.get()
    if rowid is None:
        return

    latency_ms = int((time.monotonic() - _call_start.get()) * 1000)
    input_tokens = usage.get("prompt_tokens", 0) if usage else 0
    output_tokens = usage.get("completion_tokens", 0) if usage else 0

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """UPDATE cost_ledger
           SET input_tokens = ?, output_tokens = ?, response_text = ?, latency_ms = ?
           WHERE id = ?""",
        [input_tokens, output_tokens, response_text, latency_ms, rowid],
    )
    conn.commit()
    conn.close()
    _call_rowid.set(None)


def record_quality(
    deliverable_id: str,
    quality_score: float,
    all_gates_passed: bool,
    layer_scores: dict[str, float] | None = None,
) -> None:
    """Record quality gate results for a deliverable."""
    _ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO quality_results
           (deliverable_id, quality_score, all_gates_passed, layer_scores_json, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        [deliverable_id, quality_score, 1 if all_gates_passed else 0,
         json.dumps(layer_scores) if layer_scores else None, time.time()],
    )
    conn.commit()
    conn.close()


def update_baseline(
    pipeline_name: str,
    pipeline_version: str | None = None,
    bootstrap_count: int = 20,
) -> None:
    """Recalculate cost baseline for a pipeline from ledger data."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT SUM(input_tokens + output_tokens) AS total_tokens, deliverable_id
        FROM cost_ledger WHERE pipeline_name = ?
    """
    params: list[str | None] = [pipeline_name]
    if pipeline_version:
        query += " AND pipeline_version = ?"
        params.append(pipeline_version)
    query += " GROUP BY deliverable_id"

    rows = conn.execute(query, params).fetchall()
    if len(rows) < bootstrap_count:
        conn.close()
        return

    costs = [float(row["total_tokens"]) for row in rows]
    avg = sum(costs) / len(costs)
    variance = sum((c - avg) ** 2 for c in costs) / len(costs)
    stddev = math.sqrt(variance)

    conn.execute(
        """INSERT INTO cost_baselines
           (pipeline_name, pipeline_version, avg_cost, stddev, sample_count, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(pipeline_name, pipeline_version)
           DO UPDATE SET avg_cost = ?, stddev = ?, sample_count = ?, updated_at = ?""",
        [pipeline_name, pipeline_version, avg, stddev, len(costs), time.time(),
         avg, stddev, len(costs), time.time()],
    )
    conn.commit()
    conn.close()
