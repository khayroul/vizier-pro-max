"""Deterministic bridge capture ledger for v6.2 evidence events."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Mapping, Sequence

from augments.observational.store import ensure_state_layout
from augments.observational.types import (
    BuildCaptureEvent,
    ContextType,
    EventStatus,
    EventType,
    EvidenceSource,
    JSONValue,
    Provenance,
    serialize_contract,
)

DEFAULT_STATE_ROOT = Path("state")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS build_capture_events (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    context_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def derive_event_id(namespace: str, *parts: object) -> str:
    """Derive a stable event identifier from deterministic input parts."""

    digest = hashlib.sha256(_canonical_json([namespace, *parts]).encode("utf-8")).hexdigest()
    return f"{namespace}-{digest[:16]}"


def make_event(
    *,
    source: EvidenceSource,
    context_type: ContextType,
    task_id: str,
    event_type: EventType,
    summary: str,
    status: EventStatus,
    timestamp: str,
    event_id: str | None = None,
    parent_task_id: str | None = None,
    files_touched: Sequence[str] = (),
    commands: Sequence[str] = (),
    verifications: Sequence[str] = (),
    artifacts: Sequence[str] = (),
    labels: Sequence[str] = (),
    trace_refs: Sequence[str] = (),
    metadata: Mapping[str, JSONValue] | None = None,
    provenance: Provenance | None = None,
) -> BuildCaptureEvent:
    """Construct a canonical BuildCaptureEvent without ad hoc dict payloads."""

    event_metadata = dict(metadata or {})
    if event_id is None:
        event_id = derive_event_id(
            "build-capture",
            source,
            context_type,
            task_id,
            event_type,
            summary,
            status,
            timestamp,
            parent_task_id,
            list(files_touched),
            list(commands),
            list(verifications),
            list(artifacts),
            list(labels),
            list(trace_refs),
            event_metadata,
            serialize_contract(provenance) if provenance is not None else None,
        )

    return BuildCaptureEvent(
        event_id=event_id,
        timestamp=timestamp,
        source=source,
        context_type=context_type,
        task_id=task_id,
        event_type=event_type,
        summary=summary,
        status=status,
        parent_task_id=parent_task_id,
        files_touched=tuple(files_touched),
        commands=tuple(commands),
        verifications=tuple(verifications),
        artifacts=tuple(artifacts),
        labels=tuple(labels),
        trace_refs=tuple(trace_refs),
        metadata=event_metadata,
        provenance=provenance,
    )


def append_event(
    event: BuildCaptureEvent,
    *,
    state_root: Path | str = DEFAULT_STATE_ROOT,
) -> bool:
    """Append a BuildCaptureEvent to the shared ledger if it is new."""

    layout = ensure_state_layout(state_root)
    payload = serialize_contract(event)
    payload_json = _canonical_json(payload)

    with sqlite3.connect(str(layout.build_capture_index_db)) as connection:
        connection.execute(_SCHEMA)
        try:
            connection.execute(
                """
                INSERT INTO build_capture_events (
                    event_id, timestamp, source, context_type, task_id,
                    event_type, status, summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.source,
                    event.context_type,
                    event.task_id,
                    event.event_type,
                    event.status,
                    event.summary,
                    payload_json,
                ),
            )
        except sqlite3.IntegrityError:
            return False

        with layout.build_capture_events.open("a", encoding="utf-8") as handle:
            handle.write(payload_json)
            handle.write("\n")
        connection.commit()
    return True


def read_events(
    *,
    state_root: Path | str = DEFAULT_STATE_ROOT,
) -> list[BuildCaptureEvent]:
    """Read the append-only build capture ledger as typed contract records."""

    layout = ensure_state_layout(state_root)
    if not layout.build_capture_events.exists():
        return []

    events: list[BuildCaptureEvent] = []
    for line in layout.build_capture_events.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(BuildCaptureEvent.from_dict(json.loads(line)))
    return events


def capture_external_build_event(
    *,
    source: EvidenceSource,
    task_id: str,
    event_type: EventType,
    summary: str,
    status: EventStatus,
    timestamp: str,
    state_root: Path | str = DEFAULT_STATE_ROOT,
    event_id: str | None = None,
    parent_task_id: str | None = None,
    files_touched: Sequence[str] = (),
    commands: Sequence[str] = (),
    verifications: Sequence[str] = (),
    artifacts: Sequence[str] = (),
    labels: Sequence[str] = (),
    trace_refs: Sequence[str] = (),
    metadata: Mapping[str, JSONValue] | None = None,
    provenance: Provenance | None = None,
) -> BuildCaptureEvent:
    """Create and persist an external-build BuildCaptureEvent."""

    event = make_event(
        event_id=event_id,
        source=source,
        context_type="external_build",
        task_id=task_id,
        event_type=event_type,
        summary=summary,
        status=status,
        timestamp=timestamp,
        parent_task_id=parent_task_id,
        files_touched=files_touched,
        commands=commands,
        verifications=verifications,
        artifacts=artifacts,
        labels=labels,
        trace_refs=trace_refs,
        metadata=metadata,
        provenance=provenance,
    )
    append_event(event, state_root=state_root)
    return event


__all__ = [
    "DEFAULT_STATE_ROOT",
    "append_event",
    "capture_external_build_event",
    "derive_event_id",
    "make_event",
    "read_events",
]
