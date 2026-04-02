"""Reflection rules over structured observations."""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from augments.observational.ledger import ReflectionRecord
from augments.observational.types import Observation, Provenance
from bridge.build_capture import derive_event_id


def _topic_key(observation: Observation) -> str:
    for tag in observation.tags:
        if tag.startswith("topic:"):
            return tag.split(":", 1)[1]
    if observation.applies_to:
        return f"{observation.kind}:{observation.applies_to[0].lower()}"
    return f"{observation.kind}:{observation.statement.lower().strip()}"


def _reflection_statement(observation: Observation) -> str:
    prefix_map = {
        "workflow": "Retain workflow",
        "preference": "Retain preference",
        "anti_pattern": "Avoid anti-pattern",
        "constraint": "Retain constraint",
        "failure_mode": "Guard against failure mode",
        "pattern": "Track pattern",
    }
    prefix = prefix_map.get(observation.kind, "Retain lesson")
    return f"{prefix}: {observation.statement}"


def _has_sufficient_support(observation: Observation) -> bool:
    support_count = len({*observation.episode_ids, *observation.supporting_evidence})
    return support_count >= 2


def _build_reflection(observation: Observation) -> ReflectionRecord:
    topic_key = _topic_key(observation)
    statement = _reflection_statement(observation)
    reflection_id = derive_event_id(
        "reflection",
        observation.observation_id,
        statement,
        observation.confidence,
        _has_sufficient_support(observation),
    )
    provenance = Provenance(
        event_ids=observation.provenance.event_ids if observation.provenance is not None else (),
        observation_ids=(observation.observation_id,),
        metadata={
            "kind": observation.kind,
            "topic_key": topic_key,
        },
    )
    return ReflectionRecord(
        reflection_id=reflection_id,
        observation_ids=(observation.observation_id,),
        episode_ids=observation.episode_ids,
        statement=statement,
        confidence=observation.confidence,
        status="active",
        supporting_evidence=observation.supporting_evidence or observation.episode_ids,
        tags=tuple((*observation.tags, f"topic:{topic_key}")),
        provenance=provenance,
        promoted_lesson=_has_sufficient_support(observation),
    )


def reflect_observations(
    observations: Sequence[Observation],
    *,
    existing_reflections: Sequence[ReflectionRecord] = (),
) -> list[ReflectionRecord]:
    """Reflect active observations into structured reflections and lessons."""

    current = list(existing_reflections)
    for observation in observations:
        new_reflection = _build_reflection(observation)
        topic_key = _topic_key(observation)
        updated_current: list[ReflectionRecord] = []
        replaced = False
        for existing in current:
            existing_topic = next(
                (tag.split(":", 1)[1] for tag in existing.tags if tag.startswith("topic:")),
                existing.statement.lower().strip(),
            )
            if existing.status == "active" and existing_topic == topic_key:
                if existing.statement == new_reflection.statement:
                    replaced = True
                    updated_current.append(existing)
                    continue
                updated_current.append(
                    replace(existing, status="superseded", superseded_by=new_reflection.reflection_id)
                )
            else:
                updated_current.append(existing)
        if not replaced:
            updated_current.append(new_reflection)
        current = updated_current
    return current


__all__ = ["reflect_observations"]
