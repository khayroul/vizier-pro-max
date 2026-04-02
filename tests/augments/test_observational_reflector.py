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
) -> Observation:
    return Observation(
        observation_id=observation_id,
        episode_ids=episode_ids,
        kind="workflow",
        statement=statement,
        confidence="medium",
        status="active",
        supporting_evidence=supporting_evidence,
        applies_to=("pipelines/build.py",),
        tags=("workflow", "topic:workflow:pipelines/build.py"),
        provenance=Provenance(event_ids=("evt-1",), metadata={"source": "test"}),
    )


def test_reflections_carry_confidence_support_and_promoted_lesson_threshold() -> None:
    observation = _observation(
        "obs-1",
        "Run verification and smoke tests before task completion.",
        episode_ids=("evt-1", "evt-2"),
        supporting_evidence=("pytest -q", "smoke-tests"),
    )

    [reflection] = reflect_observations([observation])

    assert reflection.confidence == "medium"
    assert reflection.supporting_evidence == ("pytest -q", "smoke-tests")
    assert reflection.promoted_lesson is True
    assert reflection.provenance is not None
    assert reflection.provenance.observation_ids == ("obs-1",)


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
