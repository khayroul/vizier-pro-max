"""Trace Exporter — anomaly detection, trace export, anomaly logging.

Checks deliverables against quality thresholds and cost baselines.
Exports full step-level traces as immutable JSON files.
Logs anomalies to anomaly_log table.
Notifies via Telegram if available (Gate 2 dependency).
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog

from middleware.cost_config import load_config

logger = structlog.get_logger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")
TRACES_DIR = str(Path(__file__).parent.parent / "traces")


def check_anomalies(
    deliverable_id: str,
    quality_threshold: float | None = None,
    anomaly_stddev: float | None = None,
) -> dict[str, Any]:
    """Check if a deliverable has anomalies.

    Args:
        deliverable_id: Unique deliverable identifier.
        quality_threshold: Override quality min score from config.
        anomaly_stddev: Override stddev multiplier from config.

    Returns:
        Dict with is_anomaly bool and reasons list.
    """
    config = load_config()
    threshold = (
        quality_threshold
        if quality_threshold is not None
        else config["quality"]["min_score"]
    )
    stddev_mult = (
        anomaly_stddev
        if anomaly_stddev is not None
        else config["baselines"]["anomaly_stddev"]
    )

    reasons: list[str] = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        qr = conn.execute(
            "SELECT quality_score FROM quality_results WHERE deliverable_id = ?",
            [deliverable_id],
        ).fetchone()
        if (
            qr
            and qr["quality_score"] is not None
            and qr["quality_score"] < threshold
        ):
            reasons.append(
                f"Quality below threshold:"
                f" {qr['quality_score']:.1f} < {threshold}"
            )

        cost_rows = conn.execute(
            """SELECT SUM(input_tokens + output_tokens) AS total_tokens, pipeline_name
               FROM cost_ledger WHERE deliverable_id = ? GROUP BY pipeline_name""",
            [deliverable_id],
        ).fetchall()

        for row in cost_rows:
            pipeline = row["pipeline_name"]
            total = row["total_tokens"]
            if pipeline is None:
                continue
            baseline = conn.execute(
                "SELECT avg_cost, stddev FROM cost_baselines WHERE pipeline_name = ?",
                [pipeline],
            ).fetchone()
            if baseline and baseline["stddev"] > 0:
                limit = baseline["avg_cost"] + stddev_mult * baseline["stddev"]
                if total > limit:
                    reasons.append(
                        f"Cost above baseline for"
                        f" {pipeline}:"
                        f" {total:.0f} > {limit:.0f}"
                    )

    return {"is_anomaly": len(reasons) > 0, "reasons": reasons}


def export_trace(deliverable_id: str) -> str:
    """Export full trace as immutable JSON.

    Args:
        deliverable_id: Unique deliverable identifier.

    Returns:
        Absolute path to the exported JSON file.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT model, pipeline_name, step_name, input_tokens, output_tokens,
                      prompt_text, response_text, latency_ms, timestamp
               FROM cost_ledger WHERE deliverable_id = ? ORDER BY timestamp""",
            [deliverable_id],
        ).fetchall()

        qr = conn.execute(
            "SELECT quality_score, all_gates_passed,"
        " layer_scores_json"
        " FROM quality_results"
        " WHERE deliverable_id = ?",
            [deliverable_id],
        ).fetchone()

    steps = [dict(row) for row in rows]
    trace = {
        "deliverable_id": deliverable_id,
        "exported_at": time.time(),
        "steps": steps,
        "quality": {
            "score": qr["quality_score"] if qr else None,
            "all_gates_passed": (
                bool(qr["all_gates_passed"]) if qr else None
            ),
            "layer_scores": (
                json.loads(qr["layer_scores_json"])
                if qr and qr["layer_scores_json"]
                else None
            ),
        },
        "total_tokens": sum(
            (s.get("input_tokens") or 0)
            + (s.get("output_tokens") or 0)
            for s in steps
        ),
    }

    traces_path = Path(TRACES_DIR)
    traces_path.mkdir(parents=True, exist_ok=True)
    output_path = traces_path / f"{deliverable_id}.json"
    output_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False))
    return str(output_path)


def log_anomaly(
    deliverable_id: str,
    client_id: str | None,
    pipeline_name: str | None,
    reasons: list[str],
    trace_path: str | None,
) -> None:
    """Record anomaly in anomaly_log table.

    Args:
        deliverable_id: Unique deliverable identifier.
        client_id: Client associated with the deliverable.
        pipeline_name: Pipeline that produced the deliverable.
        reasons: List of anomaly reason strings.
        trace_path: Path to the exported trace JSON file.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO anomaly_log
               (deliverable_id, client_id, pipeline_name,
                reasons_json, trace_path, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [deliverable_id, client_id, pipeline_name,
             json.dumps(reasons), trace_path, time.time()],
        )


def notify_anomaly(
    deliverable_id: str,
    client_id: str | None,
    pipeline_name: str | None,
    reasons: list[str],
    trace_path: str | None,
) -> None:
    """Send Telegram notification. Graceful fallback if Gate 2 not deployed.

    Args:
        deliverable_id: Unique deliverable identifier.
        client_id: Client associated with the deliverable.
        pipeline_name: Pipeline that produced the deliverable.
        reasons: List of anomaly reason strings.
        trace_path: Path to the exported trace JSON file.
    """
    message = (
        f"Anomaly detected: {deliverable_id}\n"
        f"Client: {client_id or 'unknown'}\n"
        f"Pipeline: {pipeline_name or 'unknown'}\n"
        f"Reasons: {'; '.join(reasons)}\n"
        f"Trace: {trace_path or 'N/A'}"
    )
    try:
        from scripts.delivery.send_telegram import (
            send_telegram,  # type: ignore[import-not-found]
        )
        send_telegram(message)
    except ImportError:
        logger.info(
            "Telegram not available (Gate 2)."
            " Anomaly logged: %s",
            deliverable_id,
        )


def cleanup_traces(retention_days: int | None = None) -> int:
    """Archive traces older than retention period.

    Args:
        retention_days: Override retention days from config.

    Returns:
        Number of traces archived.
    """
    config = load_config()
    days = (
        retention_days
        if retention_days is not None
        else config["traces"]["retention_days"]
    )
    archive_dir = Path(config["traces"]["archive_dir"])
    traces_dir = Path(TRACES_DIR)

    if not traces_dir.exists():
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - (days * 86400)
    archived = 0

    for trace_file in traces_dir.glob("*.json"):
        if trace_file.stat().st_mtime < cutoff:
            trace_file.rename(archive_dir / trace_file.name)
            archived += 1

    if archived:
        logger.info("Archived %d traces older than %d days", archived, days)
    return archived
