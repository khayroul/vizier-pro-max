"""Cost Ledger — Hermes lifecycle hook capturing per-call cost data.

Uses ContextVar for per-call correlation (thread/async safe).
Reads deliverable_id / client_id from deliverable_context.
Reads step_name / pipeline_name from deliverable_context when the hook is
fired by Hermes (which does not pass those fields itself). Pipelines should
call set_pipeline_step() before each LLM call so the context is available.

The ledger is also the first trustworthy meter for shared LLM traffic. Each
attempt can now record provider, source, modality, and final status rather
than only raw token counts.
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
_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _apply_alter_statement(conn: sqlite3.Connection, statement: str) -> None:
    """Apply one ALTER TABLE statement with idempotent duplicate handling."""
    try:
        conn.execute(statement.rstrip(";"))
    except sqlite3.OperationalError as exc:
        err_msg = str(exc).lower()
        if "duplicate column" in err_msg or "no such table" in err_msg:
            return
        logger.error("Unexpected ALTER TABLE error: %s", exc)
        raise


def _apply_migration(conn: sqlite3.Connection, migration_path: Path) -> None:
    """Apply one migration file, handling ALTER TABLE statements separately."""
    sql = migration_path.read_text()
    alter_statements: list[str] = []
    idempotent_lines: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("ALTER TABLE"):
            alter_statements.append(stripped)
        else:
            idempotent_lines.append(line)

    for statement in alter_statements:
        _apply_alter_statement(conn, statement)

    idempotent_sql = "\n".join(idempotent_lines).strip()
    if idempotent_sql:
        conn.executescript(idempotent_sql)


def _ensure_tables() -> None:
    """Lazily create cost_ledger tables if needed.

    Runs every SQL file in ``migrations/`` in lexical order.
    ALTER TABLE statements are executed one by one so duplicate-column cases
    remain idempotent on existing installations.
    """
    global _tables_initialized  # noqa: PLW0603
    if _tables_initialized:
        return
    with _init_lock:
        if _tables_initialized:
            return

        migration_paths = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        if not migration_paths:
            logger.warning("No migration files found in: %s", _MIGRATIONS_DIR)
            _tables_initialized = True
            return

        with sqlite3.connect(DB_PATH) as conn:
            for migration_path in migration_paths:
                _apply_migration(conn, migration_path)

        _tables_initialized = True


def record_external_usage(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    prompt_text: str | None = None,
    response_text: str | None = None,
    latency_ms: int = 0,
    deliverable_id: str | None = None,
    client_id: str | None = None,
    pipeline_name: str | None = None,
    step_name: str | None = None,
    pipeline_version: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
    modality: str | None = "chat",
    status: str = "succeeded",
    failure_reason: str | None = None,
    timestamp: float | None = None,
) -> int:
    """Insert an already-measured LLM call into the ledger."""
    _ensure_tables()
    effective_timestamp = timestamp if timestamp is not None else time.time()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO cost_ledger
               (deliverable_id, client_id, pipeline_name, step_name,
                pipeline_version, provider_name, source, modality,
                status, failure_reason, model, input_tokens, output_tokens,
                prompt_text, response_text, latency_ms, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                deliverable_id,
                client_id,
                pipeline_name,
                step_name,
                pipeline_version,
                provider_name,
                source,
                modality or "chat",
                status,
                failure_reason,
                model or "unknown",
                input_tokens,
                output_tokens,
                prompt_text,
                response_text,
                latency_ms,
                effective_timestamp,
            ],
        )
        return int(cursor.lastrowid)


def pre_llm_call(
    messages: list[dict[str, Any]],
    model: str,
    step_name: str | None = None,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
    modality: str | None = "chat",
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
                pipeline_version, provider_name, source, modality,
                status, model, prompt_text, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [deliverable_id, client_id, effective_pipeline, effective_step,
             effective_version, provider_name, source, modality or "chat",
             "started", model or "unknown", prompt_text, time.time()],
        )
        _call_rowid.set(cursor.lastrowid)

    _call_pipeline.set(effective_pipeline)


def post_llm_call(
    response: object = None,
    usage: dict[str, int] | None = None,
    status: str | None = None,
    failure_reason: str | None = None,
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
    effective_status = status or "succeeded"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """UPDATE cost_ledger
               SET input_tokens = ?, output_tokens = ?,
                   response_text = ?, latency_ms = ?,
                   status = ?, failure_reason = ?
               WHERE id = ?""",
            [
                input_tokens,
                output_tokens,
                response_text,
                latency_ms,
                effective_status,
                failure_reason,
                rowid,
            ],
        )
    _call_rowid.set(None)
    _call_start.set(0.0)

    # Auto-trigger baseline recalculation at configured interval.
    pipeline = _call_pipeline.get()
    if pipeline and effective_status == "succeeded":
        _maybe_update_baseline(pipeline)
    _call_pipeline.set(None)


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
            FROM cost_ledger
            WHERE pipeline_name = ?
              AND (status IS NULL OR status = 'succeeded')
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
