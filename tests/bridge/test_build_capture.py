"""Tests for bridge.build_capture."""
from __future__ import annotations

from pathlib import Path

from bridge.build_capture import (
    append_event,
    capture_external_build_event,
    make_event,
    read_events,
)


def test_append_event_round_trips_typed_contract_payload(tmp_path: Path) -> None:
    event = make_event(
        source="codex",
        context_type="external_build",
        task_id="packet-1",
        event_type="verification_run",
        summary="Ran bridge packet verification",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
        commands=("python3 -m pytest tests/bridge/test_build_capture.py -q",),
        trace_refs=("thread://bridge-capture",),
        metadata={"suite": "bridge"},
    )

    written = append_event(event, state_root=tmp_path / "state")

    assert written is True
    assert read_events(state_root=tmp_path / "state") == [event]
    assert (tmp_path / "state" / "build_capture" / "index.sqlite").exists()


def test_append_event_is_idempotent_for_same_event_id(tmp_path: Path) -> None:
    event = make_event(
        event_id="evt-1",
        source="vizier",
        context_type="runtime",
        task_id="task-1",
        event_type="decision_made",
        summary="Captured a runtime decision",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
    )

    assert append_event(event, state_root=tmp_path / "state") is True
    assert append_event(event, state_root=tmp_path / "state") is False
    assert read_events(state_root=tmp_path / "state") == [event]


def test_auto_derived_event_ids_remain_unique_for_repeated_observations(tmp_path: Path) -> None:
    event_a = make_event(
        source="human",
        context_type="external_build",
        task_id="bridge-watcher.manifests",
        event_type="artifact_created",
        summary="Detected 1 new or updated manifest",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
    )
    event_b = make_event(
        source="human",
        context_type="external_build",
        task_id="bridge-watcher.manifests",
        event_type="artifact_created",
        summary="Detected 1 new or updated manifest",
        status="ok",
        timestamp="2026-04-02T12:05:00+00:00",
    )
    event_c = make_event(
        source="human",
        context_type="external_build",
        task_id="bridge-watcher.manifests",
        event_type="artifact_created",
        summary="Detected 1 new or updated manifest",
        status="degraded",
        timestamp="2026-04-02T12:05:00+00:00",
    )

    assert event_a.event_id != event_b.event_id
    assert event_b.event_id != event_c.event_id

    assert append_event(event_a, state_root=tmp_path / "state") is True
    assert append_event(event_b, state_root=tmp_path / "state") is True
    assert append_event(event_c, state_root=tmp_path / "state") is True
    assert read_events(state_root=tmp_path / "state") == [event_a, event_b, event_c]


def test_capture_external_build_event_persists_external_schema(tmp_path: Path) -> None:
    event = capture_external_build_event(
        source="human",
        task_id="bridge-watcher.manifests",
        event_type="artifact_created",
        summary="Detected 1 new or updated manifest",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
        state_root=tmp_path / "state",
        files_touched=("manifests/code/tool.yaml",),
        artifacts=("tool-name",),
        labels=("watcher", "manifest_syncer"),
        metadata={"watcher": "manifest_syncer", "mtimes": {"manifests/code/tool.yaml": 1234.0}},
    )

    [loaded] = read_events(state_root=tmp_path / "state")
    assert loaded.context_type == "external_build"
    assert loaded.event_type == "artifact_created"
    assert loaded.files_touched == ("manifests/code/tool.yaml",)
    assert loaded.artifacts == ("tool-name",)
    assert loaded.metadata["watcher"] == "manifest_syncer"
    assert loaded == event
