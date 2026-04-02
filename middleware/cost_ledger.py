"""Cost Ledger — Hermes lifecycle hook capturing per-call cost data.

Uses ContextVar for per-call correlation (thread/async safe).
Reads deliverable_id / client_id from deliverable_context.
Reads step_name / pipeline_name from deliverable_context when the hook is
fired by Hermes (which does not pass those fields itself).  Pipelines should
call set_pipeline_step() before each LLM call so the context is available.
"""
from __future__ import annotations

import collections
import json
import math
import sqlite3
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import structlog

from middleware.deliverable_context import (
    get_client_id,
    get_deliverable_id,
    get_pipeline_name,
    get_pipeline_version,
    get_step_name,
)

logger = structlog.get_logger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")

# Per-call correlation — thread/async safe via ContextVar.
_call_rowid: ContextVar[int | None] = ContextVar("cost_ledger_rowid", default=None)
_call_start: ContextVar[float] = ContextVar("cost_ledger_start", default=0.0)
# Pipeline name carried from pre → post for baseline auto-trigger.
_call_pipeline: ContextVar[str | None] = ContextVar("cost_ledger_pipeline", default=None)

_init_lock = threading.Lock()
_tables_initialized = False

# Per-pipeline call counters for baseline auto-recalculation.
_baseline_counters: dict[str, int] = collections.defaultdict(int)
_counters_lock = threading.Lock()


def _ensure_tables() -> None:
    """Lazily create cost_ledger tables if needed.

    Executes the migration in two phases:
    1. ALTER TABLE prompt_log — idempotent, fails gracefully when the column
       already exists ("duplicate column") or when prompt_log hasn't been
       created yet ("no such table" — prompt_logger will create it with the
       column already included).
    2. CREATE TABLE / INDEX / VIEW statements — all use IF NOT EXISTS so they
       are fully idempotent and run unconditionally.
    """
    global _tables_initialized  # noqa: PLW0603
    if _tables_initialized:
        return
    with _init_lock:
        if _tables_initialized:
            return

        migration = Path(__file__).parent.parent / "migrations" / "001_cost_ledger.sql"
        if not migration.exists():
            logger.warning("Migration file not found: %s", migration)
            _tables_initialized = True
            return

        sql = migration.read_text()

        # Phase 1 — ALTER TABLE (best-effort, must not block phase 2).
        alter_line = "ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;"
        with sqlite3.connect(DB_PATH) as conn:
            try:
                conn.execute(alter_line.rstrip(";"))
            except sqlite3.OperationalError as exc:
                err_msg = str(exc).lower()
                if "duplicate column" in err_msg or "no such table" in err_msg:
                    pass  # idempotent — column already there or table not yet created
                else:
                    logger.error("Unexpected ALTER TABLE error: %s", exc)
                    raise

        # Phase 2 — CREATE TABLE / INDEX / VIEW (all IF NOT EXISTS = idempotent).
        idempotent_sql = "\n".join(
            line for line in sql.splitlines()
            if not line.strip().startswith("ALTER TABLE")
        )
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript(idempotent_sql)

        _tables_initialized = True


def pre_llm_call(
    messages: list[dict[str, Any]],
    model: str,
    step_name: str | None = None,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
    **kwargs: object,
) -> None:
    """Lifecycle hook — fires before every LLM call.

    step_name, pipeline_name, pipeline_version fall back to ContextVars set
    by set_pipeline_step() when Hermes fires this hook without those fields.
    """
    _ensure_tables()
    _call_start.set(time.monotonic())

    # Prefer explicit args; fall back to ContextVar (set by pipeline).
    effective_step = step_name or get_step_name()
    effective_pipeline = pipeline_name or get_pipeline_name()
    effective_version = pipeline_version or get_pipeline_version()

    deliverable_id = get_deliverable_id()
    client_id = get_client_id()
    prompt_text = json.dumps(messages, ensure_ascii=False, default=str)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO cost_ledger
               (deliverable_id, client_id, pipeline_name, step_name,
                pipeline_version, model, prompt_text, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [deliverable_id, client_id, effective_pipeline, effective_step,
             effective_version, model or "unknown", prompt_text, time.time()],
        )
        _call_rowid.set(cursor.lastrowid)

    _call_pipeline.set(effective_pipeline)


def post_llm_call(
    response: object = None,
    usage: dict[str, int] | None = None,
    **kwargs: object,
) -> None:
    """Lifecycle hook — fires after every LLM call.

    Parameter is ``response`` (not ``response_text``) to match the Hermes
    lifecycle hook API, which passes the raw response object.
    """
    rowid = _call_rowid.get()
    if rowid is None:
        return

    latency_ms = int((time.monotonic() - _call_start.get()) * 1000)
    input_tokens = usage.get("prompt_tokens", 0) if usage else 0
    output_tokens = usage.get("completion_tokens", 0) if usage else 0
    response_text = str(response) if response is not None else None

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """UPDATE cost_ledger
               SET input_tokens = ?, output_tokens = ?,
                   response_text = ?, latency_ms = ?
               WHERE id = ?""",
            [input_tokens, output_tokens, response_text, latency_ms, rowid],
        )
    _call_rowid.set(None)

    # Auto-trigger baseline recalculation at configured interval.
    pipeline = _call_pipeline.get()
    if pipeline:
        _maybe_update_baseline(pipeline)


def _maybe_update_baseline(pipeline_name: str) -> None:
    """Increment per-pipeline call counter; recalculate baseline at interval."""
    from middleware.cost_config import load_config  # local import avoids circular

    config = load_config()
    interval = int(config.get("baselines", {}).get("recalculate_interval", 10))
    bootstrap = int(config.get("baselines", {}).get("bootstrap_count", 20))

    with _counters_lock:
        _baseline_counters[pipeline_name] += 1
        count = _baseline_counters[pipeline_name]

    if count % interval == 0:
        try:
            update_baseline(pipeline_name, bootstrap_count=bootstrap)
        except sqlite3.Error as exc:
            logger.warning("Auto baseline update failed for %s: %s", pipeline_name, exc)


def record_quality(
    deliverable_id: str,
    quality_score: float,
    all_gates_passed: bool,
    layer_scores: dict[str, float] | None = None,
) -> None:
    """Record quality gate results for a deliverable.

    Uses UPSERT so only the latest score is kept per deliverable.
    """
    _ensure_tables()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO quality_results
               (deliverable_id, quality_score,
                all_gates_passed, layer_scores_json,
                timestamp)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(deliverable_id)
               DO UPDATE SET
                   quality_score = excluded.quality_score,
                   all_gates_passed = excluded.all_gates_passed,
                   layer_scores_json = excluded.layer_scores_json,
                   timestamp = excluded.timestamp""",
            [deliverable_id, quality_score, 1 if all_gates_passed else 0,
             json.dumps(layer_scores) if layer_scores else None, time.time()],
        )


def update_baseline(
    pipeline_name: str,
    pipeline_version: str | None = None,
    bootstrap_count: int = 20,
) -> None:
    """Recalculate cost baseline for a pipeline from ledger data."""
    with sqlite3.connect(DB_PATH) as conn:
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
            return

        costs = [float(row["total_tokens"]) for row in rows]
        avg = sum(costs) / len(costs)
        variance = sum((c - avg) ** 2 for c in costs) / len(costs)
        stddev = math.sqrt(variance)

        conn.execute(
            """INSERT INTO cost_baselines
               (pipeline_name, pipeline_version,
                avg_cost, stddev, sample_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(pipeline_name, pipeline_version)
               DO UPDATE SET avg_cost = ?, stddev = ?,
                             sample_count = ?,
                             updated_at = ?""",
            [pipeline_name, pipeline_version, avg, stddev, len(costs), time.time(),
             avg, stddev, len(costs), time.time()],
        )
