"""Tests for observational reflections."""
from __future__ import annotations

from augments.observational.ledger import ReflectionRecord
from augments.observational.reflector import reflect_observations
from augments.observational.types import Observation, Provenance


def _observation(
    observation_id: str,
    statement: str,
    *,
    episode_ids: tuple[str, ...],
    supporting_evidence: tuple[str, ...],
    confidence: str = "medium",
    trace_refs: tuple[str, ...] = (),
) -> Observation:
    return Observation(
        observation_id=observation_id,
        episode_ids=episode_ids,
        kind="workflow",
        statement=statement,
        confidence=confidence,
        status="active",
        supporting_evidence=supporting_evidence,
        applies_to=("pipelines/build.py",),
        tags=("workflow", "topic:workflow:pipelines/build.py"),
        provenance=Provenance(
            event_ids=episode_ids,
            trace_refs=trace_refs,
            metadata={"source": "test"},
        ),
    )


def test_reflections_carry_confidence_support_and_trace_provenance() -> None:
    observation = _observation(
        "obs-1",
        "Run verification and smoke tests before task completion.",
        episode_ids=("evt-1", "evt-2"),
        supporting_evidence=("pytest -q", "smoke-tests"),
        trace_refs=("trace://evt-1", "trace://evt-2"),
    )

    [reflection] = reflect_observations([observation])

    assert reflection.confidence == "medium"
    assert reflection.supporting_evidence == ("pytest -q", "smoke-tests")
    assert reflection.promoted_lesson is True
    assert reflection.provenance is not None
    assert reflection.provenance.observation_ids == ("obs-1",)
    assert reflection.provenance.trace_refs == ("trace://evt-1", "trace://evt-2")


def test_single_episode_reflection_is_not_promoted_lesson() -> None:
    observation = _observation(
        "obs-1",
        "Run verification before task completion.",
        episode_ids=("evt-1",),
        supporting_evidence=("pytest -q", "bridge/watcher.py"),
        trace_refs=("trace://evt-1",),
    )

    [reflection] = reflect_observations([observation])

    assert reflection.promoted_lesson is False


def test_reflections_track_supersession_for_same_topic() -> None:
    first = _observation(
        "obs-1",
        "Run verification before task completion.",
        episode_ids=("evt-1",),
        supporting_evidence=("pytest -q",),
    )
    second = _observation(
        "obs-2",
        "Run verification and smoke tests before task completion.",
        episode_ids=("evt-1", "evt-2"),
        supporting_evidence=("pytest -q", "smoke-tests"),
    )

    initial = reflect_observations([first])
    reflected = reflect_observations([second], existing_reflections=initial)

    assert len(reflected) == 2
    assert reflected[0].status == "superseded"
    assert reflected[0].superseded_by == reflected[1].reflection_id
    assert reflected[1].status == "active"
    assert reflected[1].promoted_lesson is True


def test_reflections_merge_repeated_same_statement_evidence() -> None:
    first = _observation(
        "obs-1",
        "Run verification before task completion.",
        episode_ids=("evt-1",),
        supporting_evidence=("pytest -q",),
        confidence="low",
        trace_refs=("trace://evt-1",),
    )
    second = _observation(
        "obs-2",
        "Run verification before task completion.",
        episode_ids=("evt-2",),
        supporting_evidence=("smoke-tests",),
        confidence="high",
        trace_refs=("trace://evt-2",),
    )

    initial = reflect_observations([first])
    reflected = reflect_observations([second], existing_reflections=initial)

    assert len(reflected) == 2
    assert reflected[0].status == "superseded"
    assert reflected[0].superseded_by == reflected[1].reflection_id
    assert reflected[1].status == "active"
    assert reflected[1].observation_ids == ("obs-1", "obs-2")
    assert reflected[1].episode_ids == ("evt-1", "evt-2")
    assert reflected[1].supporting_evidence == ("pytest -q", "smoke-tests")
    assert reflected[1].confidence == "high"
    assert reflected[1].promoted_lesson is True
    assert reflected[1].provenance is not None
    assert reflected[1].provenance.event_ids == ("evt-1", "evt-2")
    assert reflected[1].provenance.trace_refs == ("trace://evt-1", "trace://evt-2")
