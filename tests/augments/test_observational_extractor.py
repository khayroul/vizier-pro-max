"""Tests for observational evidence extraction."""
from __future__ import annotations

from pathlib import Path

from augments.observational.extractor import (
    events_to_episodes,
    extract_observations_from_events,
    sync_build_capture_to_ledger,
)
from augments.observational.ledger import ObservationalLedger
from bridge.build_capture import append_event, make_event


def test_events_to_episodes_and_observations_use_structured_evidence() -> None:
    verification_event = make_event(
        source="codex",
        context_type="external_build",
        task_id="task-1",
        event_type="verification_run",
        summary="Ran verification for bridge packet",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
        verifications=("python3 -m pytest tests/bridge -q",),
        files_touched=("bridge/watcher.py",),
    )
    failure_event = make_event(
        source="vizier",
        context_type="runtime",
        task_id="task-2",
        event_type="failure_seen",
        summary="Runtime capture failed on invalid JSON",
        status="error",
        timestamp="2026-04-02T12:05:00+00:00",
        files_touched=("plugins/prompt_logger.py",),
    )

    episodes = events_to_episodes([verification_event, failure_event])
    observations = extract_observations_from_events([verification_event, failure_event])

    assert [episode.episode_id for episode in episodes] == [
        verification_event.event_id,
        failure_event.event_id,
    ]
    assert [observation.kind for observation in observations] == ["workflow", "failure_mode"]
    assert observations[0].provenance is not None
    assert observations[0].provenance.event_ids == (verification_event.event_id,)
    assert observations[0].supporting_evidence == ("python3 -m pytest tests/bridge -q",)
    assert observations[1].supporting_evidence == ("plugins/prompt_logger.py",)


def test_summary_alone_does_not_produce_observation_without_structured_support() -> None:
    free_form_only = make_event(
        source="vizier",
        context_type="runtime",
        task_id="task-3",
        event_type="decision_made",
        summary="I prefer light theme for visual outputs",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
    )
    structured = make_event(
        source="vizier",
        context_type="runtime",
        task_id="task-3",
        event_type="decision_made",
        summary="I prefer light theme for visual outputs",
        status="ok",
        timestamp="2026-04-02T12:02:00+00:00",
        labels=("runtime", "prompt_logger"),
        metadata={"tool_names": ["generate_image"]},
    )

    observations = extract_observations_from_events([free_form_only, structured])

    assert len(observations) == 1
    assert observations[0].kind == "preference"
    assert observations[0].statement == "I prefer light theme for visual outputs."


def test_sync_build_capture_to_ledger_imports_bridge_evidence(tmp_path: Path) -> None:
    ledger = ObservationalLedger(state_root=tmp_path / "state")
    event = make_event(
        source="human",
        context_type="external_build",
        task_id="task-4",
        event_type="artifact_created",
        summary="Detected a new manifest artifact",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
        artifacts=("tool-name",),
        files_touched=("manifests/code/tool.yaml",),
    )
    assert append_event(event, state_root=tmp_path / "state") is True

    episodes, observations = sync_build_capture_to_ledger(
        ledger=ledger,
        state_root=tmp_path / "state",
    )

    assert len(episodes) == 1
    assert len(observations) == 1
    assert ledger.list_episodes()[0].event_id == event.event_id
    assert ledger.list_observations(status="active")[0].provenance is not None
