"""Reflection rules over structured observations."""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Sequence

from augments.observational.ledger import ReflectionRecord
from augments.observational.types import Observation, Provenance
from bridge.build_capture import derive_event_id

_CONFIDENCE_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def _merge_unique(*groups: Sequence[str]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return tuple(merged)


def _merge_metadata(*mappings: Mapping[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for mapping in mappings:
        merged.update(mapping)
    return merged


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


def _has_sufficient_support(episode_ids: Sequence[str]) -> bool:
    return len(set(episode_ids)) >= 2


def _merge_provenance(
    *,
    existing: Provenance | None,
    observation: Observation,
    topic_key: str,
) -> Provenance:
    observation_provenance = observation.provenance
    return Provenance(
        event_ids=_merge_unique(
            existing.event_ids if existing is not None else (),
            observation_provenance.event_ids if observation_provenance is not None else (),
        ),
        observation_ids=_merge_unique(
            existing.observation_ids if existing is not None else (),
            (observation.observation_id,),
        ),
        decision_packet_ids=_merge_unique(
            existing.decision_packet_ids if existing is not None else (),
            observation_provenance.decision_packet_ids if observation_provenance is not None else (),
        ),
        promotion_decision_ids=_merge_unique(
            existing.promotion_decision_ids if existing is not None else (),
            observation_provenance.promotion_decision_ids if observation_provenance is not None else (),
        ),
        trace_refs=_merge_unique(
            existing.trace_refs if existing is not None else (),
            observation_provenance.trace_refs if observation_provenance is not None else (),
        ),
        metadata=_merge_metadata(
            dict(existing.metadata) if existing is not None else {},
            dict(observation_provenance.metadata) if observation_provenance is not None else {},
            {"kind": observation.kind, "topic_key": topic_key},
        ),
    )


def _make_reflection(
    *,
    observation: Observation,
    statement: str,
    observation_ids: tuple[str, ...],
    episode_ids: tuple[str, ...],
    supporting_evidence: tuple[str, ...],
    tags: tuple[str, ...],
    confidence: str,
    provenance: Provenance,
) -> ReflectionRecord:
    topic_key = _topic_key(observation)
    promoted_lesson = _has_sufficient_support(episode_ids)
    reflection_id = derive_event_id(
        "reflection",
        topic_key,
        statement,
        confidence,
        promoted_lesson,
        list(observation_ids),
        list(episode_ids),
        list(supporting_evidence),
        list(provenance.trace_refs),
    )
    return ReflectionRecord(
        reflection_id=reflection_id,
        observation_ids=observation_ids,
        episode_ids=episode_ids,
        statement=statement,
        confidence=confidence,
        status="active",
        supporting_evidence=supporting_evidence,
        tags=tags,
        provenance=provenance,
        promoted_lesson=promoted_lesson,
    )


def _build_reflection(observation: Observation) -> ReflectionRecord:
    topic_key = _topic_key(observation)
    statement = _reflection_statement(observation)
    return _make_reflection(
        observation=observation,
        statement=statement,
        observation_ids=(observation.observation_id,),
        episode_ids=observation.episode_ids,
        supporting_evidence=observation.supporting_evidence or observation.episode_ids,
        tags=_merge_unique(observation.tags, (f"topic:{topic_key}",)),
        confidence=observation.confidence,
        provenance=_merge_provenance(existing=None, observation=observation, topic_key=topic_key),
    )


def _merge_reflection(existing: ReflectionRecord, observation: Observation) -> ReflectionRecord:
    topic_key = _topic_key(observation)
    statement = _reflection_statement(observation)
    confidence = max(existing.confidence, observation.confidence, key=_CONFIDENCE_RANK.__getitem__)
    return _make_reflection(
        observation=observation,
        statement=statement,
        observation_ids=_merge_unique(existing.observation_ids, (observation.observation_id,)),
        episode_ids=_merge_unique(existing.episode_ids, observation.episode_ids),
        supporting_evidence=_merge_unique(
            existing.supporting_evidence,
            observation.supporting_evidence or observation.episode_ids,
        ),
        tags=_merge_unique(existing.tags, observation.tags, (f"topic:{topic_key}",)),
        confidence=confidence,
        provenance=_merge_provenance(existing=existing.provenance, observation=observation, topic_key=topic_key),
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
                    merged_reflection = _merge_reflection(existing, observation)
                    replaced = True
                    if merged_reflection == existing:
                        updated_current.append(existing)
                    else:
                        updated_current.append(
                            replace(
                                existing,
                                status="superseded",
                                superseded_by=merged_reflection.reflection_id,
                            )
                        )
                        updated_current.append(merged_reflection)
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
