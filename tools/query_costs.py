"""Query Costs — model-callable Hermes tool for cost self-inspection."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import structlog

from adapter.hermes_registry import load_hermes_registry
from middleware.cost_config import calculate_cost

logger = structlog.get_logger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")


def query_costs(args: dict[str, Any], **kw: Any) -> str:
    """Query cost ledger data.

    Args:
        args: Dict with optional keys: deliverable_id, client_id, distribution,
              anomaly_history, top_steps, limit.
        **kw: Ignored extra keyword arguments.

    Returns:
        JSON string with query results or error dict.
    """
    limit = max(1, min(int(args.get("limit", 50)), 1000))
    top_steps = max(1, min(int(args.get("top_steps", 10)), 1000))

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            if args.get("deliverable_id"):
                return _per_deliverable(conn, args["deliverable_id"])
            if args.get("client_id"):
                return _per_client(conn, args["client_id"])
            if args.get("distribution"):
                return _model_distribution(conn)
            if args.get("anomaly_history"):
                return _anomaly_history(conn, limit)
            return _top_expensive_steps(conn, top_steps)

    except sqlite3.OperationalError as exc:
        return json.dumps({"error": f"Database error: {exc}"})


def _per_deliverable(conn: sqlite3.Connection, deliverable_id: str) -> str:
    """Return step-level cost breakdown for a single deliverable.

    Args:
        conn: Open SQLite connection.
        deliverable_id: The deliverable to inspect.

    Returns:
        JSON string with steps, total_tokens, and total_cost.
    """
    rows = conn.execute(
        """SELECT step_name, model, provider_name, source, modality, status,
                  failure_reason, input_tokens, output_tokens, latency_ms
           FROM cost_ledger WHERE deliverable_id = ? ORDER BY timestamp""",
        [deliverable_id],
    ).fetchall()
    steps = [dict(row) for row in rows]
    total = sum(s["input_tokens"] + s["output_tokens"] for s in steps)
    total_cost = sum(
        calculate_cost(s["model"], s["input_tokens"], s["output_tokens"])
        for s in steps
    )
    attempts_by_status: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    for step in steps:
        status = str(step.get("status") or "unknown")
        attempts_by_status[status] = attempts_by_status.get(status, 0) + 1
        provider = str(step.get("provider_name") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    return json.dumps(
        {
            "deliverable_id": deliverable_id,
            "steps": steps,
            "attempts_by_status": attempts_by_status,
            "providers": provider_counts,
            "total_tokens": total,
            "total_cost": total_cost,
        }
    )


def _per_client(conn: sqlite3.Connection, client_id: str) -> str:
    """Return cost rollup grouped by deliverable for a client.

    Args:
        conn: Open SQLite connection.
        client_id: The client to inspect.

    Returns:
        JSON string with deliverables list.
    """
    rows = conn.execute(
        """SELECT deliverable_id, SUM(input_tokens + output_tokens) AS total_tokens,
                  COUNT(*) AS step_count
           FROM cost_ledger WHERE client_id = ?
           GROUP BY deliverable_id ORDER BY MIN(timestamp) DESC""",
        [client_id],
    ).fetchall()
    return json.dumps({"client_id": client_id, "deliverables": [dict(r) for r in rows]})


def _model_distribution(conn: sqlite3.Connection) -> str:
    """Return token distribution broken down by model.

    Args:
        conn: Open SQLite connection.

    Returns:
        JSON string with models dict.
    """
    rows = conn.execute(
        """SELECT model,
                  provider_name,
                  status,
                  SUM(input_tokens) AS total_in,
                  SUM(output_tokens) AS total_out,
                  COUNT(*) AS call_count
           FROM cost_ledger
           GROUP BY model, provider_name, status""",
    ).fetchall()
    models: dict[str, dict[str, int]] = {}
    providers: dict[str, dict[str, int]] = {}
    for row in rows:
        model = str(row["model"])
        provider = str(row["provider_name"] or "unknown")
        status = str(row["status"] or "unknown")

        model_entry = models.setdefault(model, {"input": 0, "output": 0, "calls": 0})
        model_entry["input"] += int(row["total_in"] or 0)
        model_entry["output"] += int(row["total_out"] or 0)
        model_entry["calls"] += int(row["call_count"] or 0)

        provider_entry = providers.setdefault(
            provider,
            {"input": 0, "output": 0, "calls": 0, "failed_calls": 0},
        )
        provider_entry["input"] += int(row["total_in"] or 0)
        provider_entry["output"] += int(row["total_out"] or 0)
        provider_entry["calls"] += int(row["call_count"] or 0)
        if status == "failed":
            provider_entry["failed_calls"] += int(row["call_count"] or 0)

    return json.dumps({"models": models, "providers": providers})


def _anomaly_history(conn: sqlite3.Connection, limit: int) -> str:
    """Return recent anomaly log entries.

    Args:
        conn: Open SQLite connection.
        limit: Maximum number of rows to return.

    Returns:
        JSON string with anomalies list.
    """
    rows = conn.execute(
        """SELECT deliverable_id, client_id, pipeline_name,
                  reasons_json, trace_path, timestamp
           FROM anomaly_log
           ORDER BY timestamp DESC LIMIT ?""",
        [limit],
    ).fetchall()
    anomalies = []
    for row in rows:
        entry = dict(row)
        try:
            entry["reasons"] = json.loads(row["reasons_json"])
        except (json.JSONDecodeError, TypeError):
            entry["reasons"] = []
        anomalies.append(entry)
    return json.dumps({"anomalies": anomalies})


def _top_expensive_steps(conn: sqlite3.Connection, limit: int) -> str:
    """Return the N most expensive pipeline steps by total token usage.

    Args:
        conn: Open SQLite connection.
        limit: Number of steps to return.

    Returns:
        JSON string with top_steps list.
    """
    rows = conn.execute(
        """SELECT step_name, SUM(input_tokens + output_tokens) AS total_tokens,
                  COUNT(*) AS run_count, AVG(input_tokens + output_tokens) AS avg_tokens
           FROM cost_ledger WHERE step_name IS NOT NULL
           GROUP BY step_name ORDER BY total_tokens DESC LIMIT ?""",
        [limit],
    ).fetchall()
    return json.dumps({"top_steps": [dict(r) for r in rows]})


def register_query_costs_tool() -> None:
    """Register query_costs as a Hermes tool."""
    registry = load_hermes_registry()
    if registry is None:
        logger.warning("Hermes registry not available — query_costs not registered")
        return

    registry.register(
        name="query_costs",
        toolset="vizier-core",
        schema={
            "type": "object",
            "properties": {
                "deliverable_id": {
                    "type": "string",
                    "description": "Step-level cost breakdown for a deliverable",
                },
                "client_id": {
                    "type": "string",
                    "description": "Cost rollup for a client",
                },
                "distribution": {
                    "type": "boolean",
                    "description": "Token distribution by model",
                },
                "anomaly_history": {
                    "type": "boolean",
                    "description": "Recent anomaly log entries",
                },
                "top_steps": {
                    "type": "integer",
                    "description": "N most expensive steps (default 10)",
                },
            },
            "required": [],
        },
        handler=query_costs,
        check_fn=lambda: True,
        description=(
            "Inspect cost ledger: per-deliverable, per-client, model distribution,"
            " anomaly history, top expensive steps"
        ),
    )
