"""Derive structured observations from captured bridge evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from augments.observational.ledger import EpisodeRecord, ObservationalLedger
from augments.observational.types import BuildCaptureEvent, Observation, Provenance
from bridge.build_capture import derive_event_id, read_events


def _topic_key(kind: str, applies_to: Sequence[str], statement: str) -> str:
    if applies_to:
        return f"{kind}:{applies_to[0].lower()}"
    return f"{kind}:{statement.lower().strip()}"


def _supporting_evidence(event: BuildCaptureEvent) -> tuple[str, ...]:
    if event.verifications:
        return event.verifications
    if event.commands:
        return event.commands
    if event.artifacts:
        return event.artifacts
    if event.files_touched:
        return event.files_touched
    return (f"event:{event.event_id}",)


def _structured_context_present(event: BuildCaptureEvent) -> bool:
    return bool(
        event.files_touched
        or event.commands
        or event.verifications
        or event.artifacts
        or event.labels
        or event.trace_refs
        or event.metadata
    )


def _observation_from_event(event: BuildCaptureEvent) -> Observation | None:
    supporting_evidence = _supporting_evidence(event)
    applies_to = event.files_touched or event.artifacts or (event.task_id,)
    tags = [event.context_type, event.event_type]

    if event.event_type == "verification_run" and (event.verifications or event.commands):
        verification_targets = event.verifications or event.commands
        statement = (
            f"Task `{event.task_id}` validates changes with "
            f"{', '.join(f'`{item}`' for item in verification_targets)}."
        )
        kind = "workflow"
        confidence = "high" if event.status == "ok" else "medium"
        tags.append("verification")
    elif event.event_type == "failure_seen" or event.status == "error":
        file_hint = f" while touching {', '.join(f'`{path}`' for path in event.files_touched)}" if event.files_touched else ""
        statement = f"Task `{event.task_id}` can fail during `{event.event_type}`{file_hint}."
        kind = "failure_mode"
        confidence = "high" if event.status == "error" else "medium"
        tags.append("failure")
    elif event.event_type == "artifact_created" and (event.artifacts or event.files_touched):
        targets = event.artifacts or event.files_touched
        statement = (
            f"Task `{event.task_id}` emits {', '.join(f'`{item}`' for item in targets)} "
            f"as part of `{event.context_type}` execution."
        )
        kind = "workflow"
        confidence = "medium"
        tags.append("artifact")
    elif event.event_type == "decision_made" and _structured_context_present(event):
        summary_lower = event.summary.lower()
        if "prefer" in summary_lower or "preference" in summary_lower:
            kind = "preference"
        elif any(token in summary_lower for token in ("must", "never", "do not", "don't", "not ")):
            kind = "constraint"
        else:
            kind = "workflow"
        statement = event.summary.rstrip(".") + "."
        confidence = "medium" if event.status == "ok" else "low"
        tags.append("decision")
    else:
        return None

    topic_key = _topic_key(kind, applies_to, statement)
    tags.append(f"topic:{topic_key}")
    provenance = Provenance(
        event_ids=(event.event_id,),
        trace_refs=event.trace_refs,
        metadata={
            "context_type": event.context_type,
            "event_type": event.event_type,
        },
    )
    observation_id = derive_event_id(
        "observation",
        kind,
        statement,
        confidence,
        list((event.event_id,)),
    )
    return Observation(
        observation_id=observation_id,
        episode_ids=(event.event_id,),
        kind=kind,
        statement=statement,
        confidence=confidence,
        status="active",
        supporting_evidence=supporting_evidence,
        applies_to=applies_to,
        tags=tuple(tags),
        provenance=provenance,
    )


def events_to_episodes(events: Sequence[BuildCaptureEvent]) -> list[EpisodeRecord]:
    """Convert captured evidence events into canonical observational episodes."""

    return [EpisodeRecord.from_event(event) for event in events]


def extract_observations_from_events(events: Sequence[BuildCaptureEvent]) -> list[Observation]:
    """Derive structured observations from typed bridge evidence."""

    observations: list[Observation] = []
    for event in events:
        observation = _observation_from_event(event)
        if observation is not None:
            observations.append(observation)
    return observations


def sync_build_capture_to_ledger(
    *,
    ledger: ObservationalLedger,
    state_root: Path | str = Path("state"),
) -> tuple[list[EpisodeRecord], list[Observation]]:
    """Import build-capture evidence, persist episodes, and derive observations."""

    events = read_events(state_root=state_root)
    episodes = events_to_episodes(events)
    for episode in episodes:
        ledger.save_episode(episode)

    observations = extract_observations_from_events(events)
    for observation in observations:
        ledger.save_observation(observation)
    return episodes, observations


__all__ = [
    "events_to_episodes",
    "extract_observations_from_events",
    "sync_build_capture_to_ledger",
]
