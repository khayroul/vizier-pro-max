"""Tests for the observational ledger."""
from __future__ import annotations

from pathlib import Path

from augments.observational.ledger import EpisodeRecord, ObservationalLedger, ReflectionRecord
from augments.observational.types import Observation, Provenance
from bridge.build_capture import make_event


def _workflow_observation(observation_id: str, statement: str) -> Observation:
    return Observation(
        observation_id=observation_id,
        episode_ids=("evt-1",),
        kind="workflow",
        statement=statement,
        confidence="medium",
        status="active",
        supporting_evidence=("python3 -m pytest -q",),
        applies_to=("pipelines/build.py",),
        tags=("workflow", "topic:workflow:pipelines/build.py"),
        provenance=Provenance(event_ids=("evt-1",), metadata={"source": "test"}),
    )


def test_ledger_persists_episodes_observations_and_reflections(tmp_path: Path) -> None:
    ledger = ObservationalLedger(state_root=tmp_path / "state")
    event = make_event(
        source="codex",
        context_type="external_build",
        task_id="task-1",
        event_type="verification_run",
        summary="Ran packet verification",
        status="ok",
        timestamp="2026-04-02T12:00:00+00:00",
        verifications=("python3 -m pytest -q",),
    )

    episode = EpisodeRecord.from_event(event)
    assert ledger.save_episode(episode) is True
    assert ledger.list_episodes() == [episode]

    observation = _workflow_observation("obs-1", "Run verification before task completion.")
    assert ledger.save_observation(observation) is True
    assert ledger.list_observations(status="active") == [observation]

    reflection = ReflectionRecord(
        reflection_id="refl-1",
        observation_ids=("obs-1",),
        episode_ids=("evt-1",),
        statement="Retain workflow: Run verification before task completion.",
        confidence="medium",
        status="active",
        supporting_evidence=("python3 -m pytest -q",),
        tags=("topic:workflow:pipelines/build.py",),
        provenance=Provenance(observation_ids=("obs-1",), metadata={"source": "test"}),
        promoted_lesson=False,
    )
    assert ledger.save_reflection(reflection) is True
    assert ledger.list_reflections(status="active") == [reflection]


def test_ledger_tracks_supersession_for_observations_and_reflections(tmp_path: Path) -> None:
    ledger = ObservationalLedger(state_root=tmp_path / "state")

    observation_a = _workflow_observation("obs-1", "Run verification before task completion.")
    observation_b = _workflow_observation("obs-2", "Run verification and smoke tests before task completion.")

    assert ledger.save_observation(observation_a) is True
    assert ledger.save_observation(observation_b) is True

    observations = ledger.list_observations()
    assert observations[0].status == "superseded"
    assert observations[0].superseded_by == "obs-2"
    assert observations[1].status == "active"

    reflection_a = ReflectionRecord(
        reflection_id="refl-1",
        observation_ids=("obs-1",),
        episode_ids=("evt-1",),
        statement="Retain workflow: Run verification before task completion.",
        confidence="medium",
        status="active",
        supporting_evidence=("python3 -m pytest -q",),
        tags=("topic:workflow:pipelines/build.py",),
        provenance=Provenance(observation_ids=("obs-1",), metadata={"source": "test"}),
        promoted_lesson=False,
    )
    reflection_b = ReflectionRecord(
        reflection_id="refl-2",
        observation_ids=("obs-2",),
        episode_ids=("evt-1",),
        statement="Retain workflow: Run verification and smoke tests before task completion.",
        confidence="medium",
        status="active",
        supporting_evidence=("python3 -m pytest -q", "smoke-tests"),
        tags=("topic:workflow:pipelines/build.py",),
        provenance=Provenance(observation_ids=("obs-2",), metadata={"source": "test"}),
        promoted_lesson=True,
    )
    assert ledger.save_reflection(reflection_a) is True
    assert ledger.save_reflection(reflection_b) is True

    reflections = ledger.list_reflections()
    assert reflections[0].status == "superseded"
    assert reflections[0].superseded_by == "refl-2"
    assert reflections[1].status == "active"
    assert ledger.list_promoted_lessons() == [reflections[1]]
