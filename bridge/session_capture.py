"""Runtime session capture that maps prompt_log rows into BuildCaptureEvent records."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog  # type: ignore[import-untyped]

from augments.observational.types import BuildCaptureEvent
from bridge.build_capture import append_event, derive_event_id, make_event

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SessionCaptureSyncResult:
    """Result of syncing prompt_log rows into the build capture ledger."""

    events_written: int
    last_prompt_log_id: int


def _default_prompt_log_db() -> Path:
    from plugins import prompt_logger

    return Path(prompt_logger.DB_PATH)


def _load_json_sequence(raw_value: str | None) -> tuple[list[Any], list[str]]:
    if raw_value is None or raw_value == "":
        return [], []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        return [], [f"json_decode_error:{exc.msg}"]
    if parsed is None:
        return [], []
    if isinstance(parsed, list):
        return parsed, []
    return [], ["json_type_error:expected_list"]


def _extract_tool_names(tools_payload: list[Any]) -> tuple[str, ...]:
    tool_names: list[str] = []
    for tool in tools_payload:
        if isinstance(tool, str) and tool.strip():
            tool_names.append(tool)
            continue
        if isinstance(tool, dict):
            name = tool.get("name")
            if isinstance(name, str) and name.strip():
                tool_names.append(name)
    return tuple(tool_names)


def _row_timestamp_to_iso(timestamp_value: Any) -> str:
    return datetime.fromtimestamp(float(timestamp_value), tz=UTC).isoformat()


def prompt_log_row_to_event(row: sqlite3.Row) -> BuildCaptureEvent:
    """Map a prompt_log row to the canonical runtime BuildCaptureEvent."""

    prompt_log_id = int(row["id"])
    task_id = str(row["task_id"] or f"prompt-log-{prompt_log_id}")
    step = int(row["step"] or 0)
    model = str(row["model"] or "unknown")
    timestamp = _row_timestamp_to_iso(row["timestamp"])
    messages, message_errors = _load_json_sequence(row["messages_json"])
    tools, tool_errors = _load_json_sequence(row["tools_json"])
    tool_names = _extract_tool_names(tools)
    parse_errors = message_errors + tool_errors
    status = "degraded" if parse_errors else "ok"
    summary = (
        f"Runtime decision captured for task {task_id} step {step}"
        if not parse_errors
        else f"Runtime decision captured with degraded prompt_log payload for task {task_id} step {step}"
    )
    metadata: dict[str, object] = {
        "prompt_log_id": prompt_log_id,
        "step": step,
        "model": model,
        "message_count": len(messages),
        "tool_names": list(tool_names),
        "tokens_in": int(row["tokens_in"] or 0),
        "tokens_out": int(row["tokens_out"] or 0),
    }
    deliverable_id = row["deliverable_id"]
    if deliverable_id:
        metadata["deliverable_id"] = str(deliverable_id)
    if parse_errors:
        metadata["parse_errors"] = parse_errors

    return make_event(
        event_id=derive_event_id("runtime-decision", prompt_log_id, task_id, step, model),
        source="vizier",
        context_type="runtime",
        task_id=task_id,
        event_type="decision_made",
        summary=summary,
        status=status,
        timestamp=timestamp,
        labels=("runtime", "prompt_logger"),
        trace_refs=(f"prompt_log:{prompt_log_id}",),
        metadata=metadata,
    )


def sync_prompt_log_to_build_capture(
    *,
    prompt_log_db: Path | str | None = None,
    state_root: Path | str = Path("state"),
    after_row_id: int = 0,
) -> SessionCaptureSyncResult:
    """Sync prompt_log rows into the append-only build capture ledger."""

    db_path = Path(prompt_log_db) if prompt_log_db is not None else _default_prompt_log_db()
    if not db_path.exists():
        return SessionCaptureSyncResult(events_written=0, last_prompt_log_id=after_row_id)

    with sqlite3.connect(str(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(prompt_log)").fetchall()
        }
        deliverable_select = "deliverable_id" if "deliverable_id" in columns else "NULL AS deliverable_id"
        try:
            rows = connection.execute(
                f"""
                SELECT id, task_id, step, model, messages_json, tools_json,
                       timestamp, tokens_in, tokens_out, {deliverable_select}
                FROM prompt_log
                WHERE id > ?
                ORDER BY id ASC
                """,
                (after_row_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return SessionCaptureSyncResult(events_written=0, last_prompt_log_id=after_row_id)
            raise

    events_written = 0
    last_prompt_log_id = after_row_id
    for row in rows:
        event = prompt_log_row_to_event(row)
        if append_event(event, state_root=state_root):
            events_written += 1
        last_prompt_log_id = int(row["id"])

    logger.info(
        "session_capture_sync_complete",
        events_written=events_written,
        last_prompt_log_id=last_prompt_log_id,
        prompt_log_db=str(db_path),
    )
    return SessionCaptureSyncResult(
        events_written=events_written,
        last_prompt_log_id=last_prompt_log_id,
    )


__all__ = [
    "SessionCaptureSyncResult",
    "prompt_log_row_to_event",
    "sync_prompt_log_to_build_capture",
]
