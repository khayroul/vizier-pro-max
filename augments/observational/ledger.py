"""SQLite-backed canonical storage for observational memory."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from augments.observational.store import ensure_state_layout
from augments.observational.types import (
    BuildCaptureEvent,
    ContractValidationError,
    EventStatus,
    EventType,
    EvidenceSource,
    JSONValue,
    Observation,
    ObservationStatus,
    Provenance,
    serialize_contract,
)


def _json_safe(value: Any) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Provenance):
        return serialize_contract(value)
    if is_dataclass(value):
        return {
            field_info.name: _json_safe(getattr(value, field_info.name))
            for field_info in fields(value)
            if getattr(value, field_info.name) is not None
        }
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _canonical_json(payload: Mapping[str, JSONValue]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class EpisodeRecord:
    """One persisted evidence episode derived from build-capture."""

    episode_id: str
    event_id: str
    timestamp: str
    source: EvidenceSource
    context_type: str
    task_id: str
    event_type: EventType
    summary: str
    status: EventStatus
    files_touched: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    verifications: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()
    metadata: Mapping[str, JSONValue] | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ContractValidationError("episode_id must be a non-empty string")
        if self.episode_id != self.event_id:
            raise ContractValidationError("episode_id must match event_id for captured episodes")
        if not self.summary.strip():
            raise ContractValidationError("summary must be a non-empty string")

    def to_dict(self) -> dict[str, JSONValue]:
        return _json_safe(self)  # type: ignore[return-value]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EpisodeRecord:
        provenance = payload.get("provenance")
        return cls(
            episode_id=str(payload["episode_id"]),
            event_id=str(payload["event_id"]),
            timestamp=str(payload["timestamp"]),
            source=str(payload["source"]),
            context_type=str(payload["context_type"]),
            task_id=str(payload["task_id"]),
            event_type=str(payload["event_type"]),
            summary=str(payload["summary"]),
            status=str(payload["status"]),
            files_touched=tuple(payload.get("files_touched", ())),
            commands=tuple(payload.get("commands", ())),
            verifications=tuple(payload.get("verifications", ())),
            artifacts=tuple(payload.get("artifacts", ())),
            labels=tuple(payload.get("labels", ())),
            trace_refs=tuple(payload.get("trace_refs", ())),
            metadata=payload.get("metadata"),
            provenance=Provenance.from_dict(provenance) if isinstance(provenance, Mapping) else None,
        )

    @classmethod
    def from_event(cls, event: BuildCaptureEvent) -> EpisodeRecord:
        return cls(
            episode_id=event.event_id,
            event_id=event.event_id,
            timestamp=event.timestamp,
            source=event.source,
            context_type=event.context_type,
            task_id=event.task_id,
            event_type=event.event_type,
            summary=event.summary,
            status=event.status,
            files_touched=event.files_touched,
            commands=event.commands,
            verifications=event.verifications,
            artifacts=event.artifacts,
            labels=event.labels,
            trace_refs=event.trace_refs,
            metadata=_json_safe(event.metadata) if event.metadata else None,
            provenance=event.provenance,
        )


@dataclass(frozen=True, slots=True)
class ReflectionRecord:
    """A structured reflection derived from one or more observations."""

    reflection_id: str
    observation_ids: tuple[str, ...]
    episode_ids: tuple[str, ...]
    statement: str
    confidence: str
    status: ObservationStatus
    supporting_evidence: tuple[str, ...]
    superseded_by: str | None = None
    tags: tuple[str, ...] = ()
    provenance: Provenance | None = None
    promoted_lesson: bool = False

    def __post_init__(self) -> None:
        if not self.reflection_id.strip():
            raise ContractValidationError("reflection_id must be a non-empty string")
        if not self.observation_ids:
            raise ContractValidationError("reflection must reference at least one observation")
        if not self.episode_ids:
            raise ContractValidationError("reflection must reference at least one episode")
        if not self.statement.strip():
            raise ContractValidationError("reflection statement must be a non-empty string")
        if self.confidence not in {"low", "medium", "high"}:
            raise ContractValidationError("reflection confidence must be one of ('low', 'medium', 'high')")
        if self.status not in {"active", "superseded", "rejected"}:
            raise ContractValidationError("reflection status must be one of ('active', 'superseded', 'rejected')")
        if not self.supporting_evidence:
            raise ContractValidationError("reflection supporting_evidence must not be empty")
        if self.status == "superseded" and self.superseded_by is None:
            raise ContractValidationError("superseded reflections must set superseded_by")
        if self.status != "superseded" and self.superseded_by is not None:
            raise ContractValidationError("superseded_by is only valid when status='superseded'")

    def to_dict(self) -> dict[str, JSONValue]:
        return _json_safe(self)  # type: ignore[return-value]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ReflectionRecord:
        provenance = payload.get("provenance")
        return cls(
            reflection_id=str(payload["reflection_id"]),
            observation_ids=tuple(payload["observation_ids"]),
            episode_ids=tuple(payload["episode_ids"]),
            statement=str(payload["statement"]),
            confidence=str(payload["confidence"]),
            status=str(payload["status"]),
            supporting_evidence=tuple(payload["supporting_evidence"]),
            superseded_by=payload.get("superseded_by"),
            tags=tuple(payload.get("tags", ())),
            provenance=Provenance.from_dict(provenance) if isinstance(provenance, Mapping) else None,
            promoted_lesson=bool(payload.get("promoted_lesson", False)),
        )


def _observation_topic_key(observation: Observation) -> str:
    for tag in observation.tags:
        if tag.startswith("topic:"):
            return tag.split(":", 1)[1]
    if observation.applies_to:
        return f"{observation.kind}:{observation.applies_to[0].lower()}"
    return f"{observation.kind}:{observation.statement.lower().strip()}"


def _reflection_topic_key(reflection: ReflectionRecord) -> str:
    for tag in reflection.tags:
        if tag.startswith("topic:"):
            return tag.split(":", 1)[1]
    return reflection.statement.lower().strip()


def _update_observation_status(
    existing: Observation,
    replacement_id: str,
) -> Observation:
    return replace(existing, status="superseded", superseded_by=replacement_id)


def _update_reflection_status(
    existing: ReflectionRecord,
    replacement_id: str,
) -> ReflectionRecord:
    return replace(existing, status="superseded", superseded_by=replacement_id)


class ObservationalLedger:
    """Canonical SQLite-backed storage for episodes, observations, and reflections."""

    _EPISODE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS episodes (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        episode_id TEXT NOT NULL UNIQUE,
        event_id TEXT NOT NULL UNIQUE,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    """
    _OBSERVATION_SCHEMA = """
    CREATE TABLE IF NOT EXISTS observations (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT NOT NULL UNIQUE,
        topic_key TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    """
    _REFLECTION_SCHEMA = """
    CREATE TABLE IF NOT EXISTS reflections (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        reflection_id TEXT NOT NULL UNIQUE,
        topic_key TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence TEXT NOT NULL,
        promoted_lesson INTEGER NOT NULL,
        payload_json TEXT NOT NULL
    );
    """

    def __init__(self, *, state_root: Path | str = Path("state")) -> None:
        self._layout = ensure_state_layout(state_root)
        self._migrate()

    def _connect(self, db_path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(str(db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self) -> None:
        with self._connect(self._layout.observational_episodes_db) as connection:
            connection.execute(self._EPISODE_SCHEMA)
            connection.commit()
        with self._connect(self._layout.observational_observations_db) as connection:
            connection.execute(self._OBSERVATION_SCHEMA)
            connection.commit()
        with self._connect(self._layout.observational_reflections_db) as connection:
            connection.execute(self._REFLECTION_SCHEMA)
            connection.commit()

    def save_episode(self, episode: EpisodeRecord) -> bool:
        payload_json = _canonical_json(episode.to_dict())
        with self._connect(self._layout.observational_episodes_db) as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO episodes (episode_id, event_id, timestamp, status, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        episode.episode_id,
                        episode.event_id,
                        episode.timestamp,
                        episode.status,
                        payload_json,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
            connection.commit()
        return True

    def save_observation(self, observation: Observation) -> bool:
        topic_key = _observation_topic_key(observation)
        payload_json = _canonical_json(serialize_contract(observation))
        with self._connect(self._layout.observational_observations_db) as connection:
            existing_row = connection.execute(
                """
                SELECT payload_json
                FROM observations
                WHERE topic_key = ? AND status = 'active'
                ORDER BY row_id DESC
                LIMIT 1
                """,
                (topic_key,),
            ).fetchone()
            if existing_row is not None:
                existing = Observation.from_dict(json.loads(existing_row["payload_json"]))
                if existing.observation_id == observation.observation_id:
                    return False
                superseded = _update_observation_status(existing, observation.observation_id)
                connection.execute(
                    """
                    UPDATE observations
                    SET status = ?, payload_json = ?
                    WHERE observation_id = ?
                    """,
                    (
                        superseded.status,
                        _canonical_json(serialize_contract(superseded)),
                        superseded.observation_id,
                    ),
                )
            try:
                connection.execute(
                    """
                    INSERT INTO observations (observation_id, topic_key, status, confidence, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        observation.observation_id,
                        topic_key,
                        observation.status,
                        observation.confidence,
                        payload_json,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
            connection.commit()
        return True

    def save_reflection(self, reflection: ReflectionRecord) -> bool:
        topic_key = _reflection_topic_key(reflection)
        payload_json = _canonical_json(reflection.to_dict())
        with self._connect(self._layout.observational_reflections_db) as connection:
            existing_row = connection.execute(
                """
                SELECT payload_json
                FROM reflections
                WHERE topic_key = ? AND status = 'active'
                ORDER BY row_id DESC
                LIMIT 1
                """,
                (topic_key,),
            ).fetchone()
            if existing_row is not None:
                existing = ReflectionRecord.from_dict(json.loads(existing_row["payload_json"]))
                if existing.reflection_id == reflection.reflection_id:
                    return False
                superseded = _update_reflection_status(existing, reflection.reflection_id)
                connection.execute(
                    """
                    UPDATE reflections
                    SET status = ?, promoted_lesson = ?, payload_json = ?
                    WHERE reflection_id = ?
                    """,
                    (
                        superseded.status,
                        1 if superseded.promoted_lesson else 0,
                        _canonical_json(superseded.to_dict()),
                        superseded.reflection_id,
                    ),
                )
            try:
                connection.execute(
                    """
                    INSERT INTO reflections (
                        reflection_id, topic_key, status, confidence, promoted_lesson, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reflection.reflection_id,
                        topic_key,
                        reflection.status,
                        reflection.confidence,
                        1 if reflection.promoted_lesson else 0,
                        payload_json,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
            connection.commit()
        return True

    def list_episodes(self) -> list[EpisodeRecord]:
        with self._connect(self._layout.observational_episodes_db) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM episodes ORDER BY row_id ASC"
            ).fetchall()
        return [EpisodeRecord.from_dict(json.loads(row["payload_json"])) for row in rows]

    def list_observations(self, *, status: ObservationStatus | None = None) -> list[Observation]:
        query = "SELECT payload_json FROM observations"
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY row_id ASC"
        with self._connect(self._layout.observational_observations_db) as connection:
            rows = connection.execute(query, params).fetchall()
        return [Observation.from_dict(json.loads(row["payload_json"])) for row in rows]

    def list_reflections(
        self,
        *,
        status: ObservationStatus | None = None,
        promoted_lesson_only: bool = False,
    ) -> list[ReflectionRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if promoted_lesson_only:
            clauses.append("promoted_lesson = 1")
        query = "SELECT payload_json FROM reflections"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY row_id ASC"
        with self._connect(self._layout.observational_reflections_db) as connection:
            rows = connection.execute(query, params).fetchall()
        return [ReflectionRecord.from_dict(json.loads(row["payload_json"])) for row in rows]

    def list_promoted_lessons(self) -> list[ReflectionRecord]:
        return self.list_reflections(status="active", promoted_lesson_only=True)


__all__ = [
    "EpisodeRecord",
    "ObservationalLedger",
    "ReflectionRecord",
]
