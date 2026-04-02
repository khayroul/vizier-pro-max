"""Tests for the canonical v6.2 observational contracts."""
from __future__ import annotations

from typing import Any

import pytest

from augments.observational.types import (
    BuildCaptureEvent,
    CandidateArtifact,
    ContractValidationError,
    DecisionPacket,
    Observation,
    PromotionDecision,
    Provenance,
    serialize_contract,
)


def test_build_capture_event_round_trip_normalizes_sequences_and_provenance() -> None:
    payload: dict[str, Any] = {
        "event_id": "evt-1",
        "timestamp": "2026-04-02T10:30:00+08:00",
        "source": "codex",
        "context_type": "external_build",
        "task_id": "task-1",
        "event_type": "verification_run",
        "summary": "Ran packet-scoped checks",
        "status": "ok",
        "files_touched": ["augments/observational/types.py"],
        "commands": ["python3 -m pytest tests/augments/test_observational_types.py -q"],
        "metadata": {"attempt": 1, "labels": ["packet", "contracts-ledger"]},
        "provenance": {"trace_refs": ["thread://contracts-ledger"], "metadata": {"session": "worker-1"}},
    }

    event = BuildCaptureEvent.from_dict(payload)

    assert event.files_touched == ("augments/observational/types.py",)
    assert event.commands == ("python3 -m pytest tests/augments/test_observational_types.py -q",)
    assert event.provenance == Provenance(
        trace_refs=("thread://contracts-ledger",),
        metadata={"session": "worker-1"},
    )
    assert serialize_contract(event) == {
        **payload,
        "files_touched": ["augments/observational/types.py"],
        "commands": ["python3 -m pytest tests/augments/test_observational_types.py -q"],
    }


def test_decision_packet_requires_known_status_and_non_empty_sequences() -> None:
    with pytest.raises(ContractValidationError, match="status must be one of"):
        DecisionPacket(
            packet_id="packet-1",
            source_event_ids=("evt-1",),
            problem="Need deterministic candidate routing.",
            proposed_change="Freeze the shared ledger contracts.",
            verification_plan=("run unit tests",),
            candidate_targets=("state/candidates/routing/router.yaml",),
            status="pending",  # type: ignore[arg-type]
        )

    with pytest.raises(ContractValidationError, match="source_event_ids must contain at least one item"):
        DecisionPacket(
            packet_id="packet-1",
            source_event_ids=(),
            problem="Need deterministic candidate routing.",
            proposed_change="Freeze the shared ledger contracts.",
            verification_plan=("run unit tests",),
            candidate_targets=("state/candidates/routing/router.yaml",),
            status="draft",
        )


def test_observation_enforces_supersession_contract() -> None:
    with pytest.raises(ContractValidationError, match="superseded observations must set superseded_by"):
        Observation(
            observation_id="obs-1",
            episode_ids=("evt-1",),
            kind="pattern",
            statement="Bridge events cluster around verification failures.",
            confidence="high",
            status="superseded",
        )

    observation = Observation(
        observation_id="obs-2",
        episode_ids=("evt-1", "evt-2"),
        kind="workflow",
        statement="Promote only after replay and benchmark verification.",
        confidence="high",
        status="superseded",
        superseded_by="obs-3",
        provenance=Provenance(event_ids=("evt-1",), metadata={"rule": "append-first"}),
    )

    assert observation.superseded_by == "obs-3"


def test_candidate_artifact_must_live_under_matching_state_candidate_family() -> None:
    artifact = CandidateArtifact(
        candidate_id="cand-1",
        artifact_type="pipeline",
        source="openspace",
        candidate_path="state/candidates/pipelines/retry_pipeline.py",
        intended_target="pipelines/retry_pipeline.py",
        status="draft",
        provenance=Provenance(decision_ids=("packet-1",), metadata={"generator": "openspace"}),
    )

    assert artifact.candidate_path == "state/candidates/pipelines/retry_pipeline.py"

    with pytest.raises(ContractValidationError, match="candidate_path must live under state/candidates/pipelines/"):
        CandidateArtifact(
            candidate_id="cand-2",
            artifact_type="pipeline",
            source="openspace",
            candidate_path="state/candidates/prompts/retry_pipeline.py",
            intended_target="pipelines/retry_pipeline.py",
            status="draft",
        )


def test_promotion_decision_serializes_json_safe_results() -> None:
    decision = PromotionDecision(
        decision_id="dec-1",
        candidate_id="cand-1",
        outcome="held",
        timestamp="2026-04-02T11:00:00+08:00",
        reasons=("Replay has one degraded trace.",),
        replay_results={"passed": 4, "failed": 1, "cases": ["smoke", "replay"]},
        benchmark_results={"score": 0.92},
        provenance=Provenance(
            decision_ids=("packet-1",),
            trace_refs=("selfbuild://replay/2026-04-02-1",),
        ),
    )

    payload = serialize_contract(decision)
    assert payload["replay_results"] == {"passed": 4, "failed": 1, "cases": ["smoke", "replay"]}
    assert payload["benchmark_results"] == {"score": 0.92}
