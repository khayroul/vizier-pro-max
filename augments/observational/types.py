"""Canonical observational contracts for the Vizier v6.2 packets."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Mapping, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
FrozenJSONValue: TypeAlias = JSONScalar | tuple["FrozenJSONValue", ...] | Mapping[str, "FrozenJSONValue"]

EvidenceSource: TypeAlias = Literal["human", "codex", "claude", "vizier"]
ContextType: TypeAlias = Literal["external_build", "runtime", "selfbuild", "evolution"]
EventType: TypeAlias = Literal[
    "task_started",
    "decision_made",
    "file_changed",
    "command_run",
    "verification_run",
    "failure_seen",
    "artifact_created",
    "task_completed",
]
EventStatus: TypeAlias = Literal["ok", "degraded", "error"]
DecisionPacketStatus: TypeAlias = Literal[
    "draft",
    "ready_for_reflection",
    "ready_for_candidate",
    "archived",
]
ObservationKind: TypeAlias = Literal[
    "pattern",
    "preference",
    "anti_pattern",
    "workflow",
    "constraint",
    "failure_mode",
]
ConfidenceLevel: TypeAlias = Literal["low", "medium", "high"]
ObservationStatus: TypeAlias = Literal["active", "superseded", "rejected"]
ArtifactType: TypeAlias = Literal[
    "skill",
    "prompt",
    "template",
    "pipeline",
    "routing",
    "distillation_program",
]
CandidateSource: TypeAlias = Literal["bridge", "openspace", "distillation", "manual"]
CandidateStatus: TypeAlias = Literal["draft", "under_evaluation", "held", "rejected", "promoted"]
PromotionOutcome: TypeAlias = Literal["promoted", "held", "rejected", "archived"]

CANDIDATE_DIR_BY_ARTIFACT_TYPE: Mapping[ArtifactType, str] = MappingProxyType(
    {
        "skill": "skills",
        "prompt": "prompts",
        "template": "templates",
        "pipeline": "pipelines",
        "routing": "routing",
        "distillation_program": "distillation",
    }
)


class ContractValidationError(ValueError):
    """Raised when a contract payload violates the shared v6.2 rules."""


class ContractModel:
    """Small serialization mixin for the canonical contract dataclasses."""

    def to_dict(self) -> dict[str, JSONValue]:
        return serialize_contract(self)


def _freeze_json(value: Any, field_name: str) -> FrozenJSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, f"{field_name}[]") for item in value)
    if isinstance(value, Mapping):
        frozen: dict[str, FrozenJSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ContractValidationError(f"{field_name} keys must be non-empty strings")
            frozen[key] = _freeze_json(item, f"{field_name}.{key}")
        return MappingProxyType(frozen)
    raise ContractValidationError(f"{field_name} must be JSON-serializable")


def _thaw_json(value: FrozenJSONValue | Provenance | ContractModel | Any) -> JSONValue:
    if is_dataclass(value):
        return serialize_contract(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    raise ContractValidationError("Unsupported frozen JSON value")


def _validate_required_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")
    return value


def _validate_optional_text(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _validate_required_text(field_name, value)


def _validate_iso_timestamp(field_name: str, value: Any) -> str:
    text = _validate_required_text(field_name, value)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be an ISO-8601 timestamp") from exc
    return text


def _validate_literal(field_name: str, value: Any, allowed: tuple[str, ...]) -> str:
    text = _validate_required_text(field_name, value)
    if text not in allowed:
        raise ContractValidationError(f"{field_name} must be one of {allowed}")
    return text


def _normalize_string_tuple(
    field_name: str,
    value: Any,
    *,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    if value is None:
        if require_non_empty:
            raise ContractValidationError(f"{field_name} must contain at least one item")
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"{field_name} must be a sequence of non-empty strings")
    items = tuple(_validate_required_text(f"{field_name}[{index}]", item) for index, item in enumerate(value))
    if require_non_empty and not items:
        raise ContractValidationError(f"{field_name} must contain at least one item")
    return items


def _normalize_mapping(
    field_name: str,
    value: Any,
    *,
    allow_none: bool = False,
) -> Mapping[str, FrozenJSONValue] | None:
    if value is None:
        return None if allow_none else MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be a mapping")
    frozen = _freeze_json(value, field_name)
    if not isinstance(frozen, Mapping):
        raise ContractValidationError(f"{field_name} must be a JSON object")
    return frozen


def _normalize_provenance(value: Any) -> Provenance | None:
    if value is None:
        return None
    if isinstance(value, Provenance):
        return value
    if isinstance(value, Mapping):
        return Provenance.from_dict(value)
    raise ContractValidationError("provenance must be a provenance mapping")


def _validate_confidence_score(field_name: str, value: Any) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ContractValidationError(f"{field_name} must be a float between 0.0 and 1.0")
    score = float(value)
    if score < 0.0 or score > 1.0:
        raise ContractValidationError(f"{field_name} must be between 0.0 and 1.0")
    return score


def _validate_candidate_path(artifact_type: ArtifactType, candidate_path: Any) -> str:
    text = _validate_required_text("candidate_path", candidate_path)
    path = PurePosixPath(text)
    expected_root = PurePosixPath("state", "candidates", CANDIDATE_DIR_BY_ARTIFACT_TYPE[artifact_type])
    if path.is_absolute():
        raise ContractValidationError("candidate_path must be repo-relative, not absolute")
    if any(part in {"..", "."} for part in path.parts):
        raise ContractValidationError("candidate_path must not contain path traversal segments")
    if path.parts[: len(expected_root.parts)] != expected_root.parts:
        raise ContractValidationError(
            "candidate_path must live under "
            f"{expected_root.as_posix()}/ for artifact_type={artifact_type}"
        )
    if len(path.parts) <= len(expected_root.parts):
        raise ContractValidationError("candidate_path must identify a concrete candidate artifact location")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class Provenance(ContractModel):
    """Shared provenance surface reused by downstream architectural records."""

    event_ids: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    decision_packet_ids: tuple[str, ...] = ()
    promotion_decision_ids: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()
    metadata: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        event_ids = _normalize_string_tuple("event_ids", self.event_ids)
        observation_ids = _normalize_string_tuple("observation_ids", self.observation_ids)
        decision_packet_ids = _normalize_string_tuple("decision_packet_ids", self.decision_packet_ids)
        promotion_decision_ids = _normalize_string_tuple(
            "promotion_decision_ids",
            self.promotion_decision_ids,
        )
        trace_refs = _normalize_string_tuple("trace_refs", self.trace_refs)
        metadata = _normalize_mapping("metadata", self.metadata)
        if not any((event_ids, observation_ids, decision_packet_ids, promotion_decision_ids, trace_refs, metadata)):
            raise ContractValidationError("provenance must contain at least one reference or metadata entry")
        object.__setattr__(self, "event_ids", event_ids)
        object.__setattr__(self, "observation_ids", observation_ids)
        object.__setattr__(self, "decision_packet_ids", decision_packet_ids)
        object.__setattr__(self, "promotion_decision_ids", promotion_decision_ids)
        object.__setattr__(self, "trace_refs", trace_refs)
        object.__setattr__(self, "metadata", metadata)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Provenance:
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True)
class BuildCaptureEvent(ContractModel):
    """One captured runtime or apprenticeship event."""

    STATUS_VALUES: ClassVar[tuple[str, ...]] = ("ok", "degraded", "error")
    SOURCE_VALUES: ClassVar[tuple[str, ...]] = ("human", "codex", "claude", "vizier")
    CONTEXT_VALUES: ClassVar[tuple[str, ...]] = ("external_build", "runtime", "selfbuild", "evolution")
    EVENT_VALUES: ClassVar[tuple[str, ...]] = (
        "task_started",
        "decision_made",
        "file_changed",
        "command_run",
        "verification_run",
        "failure_seen",
        "artifact_created",
        "task_completed",
    )

    event_id: str
    timestamp: str
    source: EvidenceSource
    context_type: ContextType
    task_id: str
    event_type: EventType
    summary: str
    status: EventStatus
    parent_task_id: str | None = None
    files_touched: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    verifications: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()
    metadata: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _validate_required_text("event_id", self.event_id))
        object.__setattr__(self, "timestamp", _validate_iso_timestamp("timestamp", self.timestamp))
        object.__setattr__(self, "source", _validate_literal("source", self.source, self.SOURCE_VALUES))
        object.__setattr__(
            self,
            "context_type",
            _validate_literal("context_type", self.context_type, self.CONTEXT_VALUES),
        )
        object.__setattr__(self, "task_id", _validate_required_text("task_id", self.task_id))
        object.__setattr__(self, "event_type", _validate_literal("event_type", self.event_type, self.EVENT_VALUES))
        object.__setattr__(self, "summary", _validate_required_text("summary", self.summary))
        object.__setattr__(self, "status", _validate_literal("status", self.status, self.STATUS_VALUES))
        object.__setattr__(self, "parent_task_id", _validate_optional_text("parent_task_id", self.parent_task_id))
        object.__setattr__(self, "files_touched", _normalize_string_tuple("files_touched", self.files_touched))
        object.__setattr__(self, "commands", _normalize_string_tuple("commands", self.commands))
        object.__setattr__(self, "verifications", _normalize_string_tuple("verifications", self.verifications))
        object.__setattr__(self, "artifacts", _normalize_string_tuple("artifacts", self.artifacts))
        object.__setattr__(self, "labels", _normalize_string_tuple("labels", self.labels))
        object.__setattr__(self, "trace_refs", _normalize_string_tuple("trace_refs", self.trace_refs))
        object.__setattr__(self, "metadata", _normalize_mapping("metadata", self.metadata))
        provenance = _normalize_provenance(self.provenance)
        if provenance is not None and provenance.trace_refs:
            raise ContractValidationError(
                "BuildCaptureEvent trace_refs must use the top-level field, not provenance.trace_refs"
            )
        object.__setattr__(self, "provenance", provenance)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BuildCaptureEvent:
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True)
class DecisionPacket(ContractModel):
    """Normalized decision handoff between capture and later governance packets."""

    STATUS_VALUES: ClassVar[tuple[str, ...]] = (
        "draft",
        "ready_for_reflection",
        "ready_for_candidate",
        "archived",
    )

    decision_packet_id: str
    source_event_ids: tuple[str, ...]
    problem: str
    proposed_change: str
    verification_plan: tuple[str, ...]
    candidate_targets: tuple[str, ...]
    status: DecisionPacketStatus
    evidence: tuple[str, ...] = ()
    risk_tier: str | None = None
    confidence: float | None = None
    notes: tuple[str, ...] = ()
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_packet_id",
            _validate_required_text("decision_packet_id", self.decision_packet_id),
        )
        object.__setattr__(
            self,
            "source_event_ids",
            _normalize_string_tuple("source_event_ids", self.source_event_ids, require_non_empty=True),
        )
        object.__setattr__(self, "problem", _validate_required_text("problem", self.problem))
        object.__setattr__(self, "proposed_change", _validate_required_text("proposed_change", self.proposed_change))
        object.__setattr__(
            self,
            "verification_plan",
            _normalize_string_tuple("verification_plan", self.verification_plan, require_non_empty=True),
        )
        object.__setattr__(
            self,
            "candidate_targets",
            _normalize_string_tuple("candidate_targets", self.candidate_targets, require_non_empty=True),
        )
        object.__setattr__(self, "status", _validate_literal("status", self.status, self.STATUS_VALUES))
        object.__setattr__(self, "evidence", _normalize_string_tuple("evidence", self.evidence))
        object.__setattr__(self, "risk_tier", _validate_optional_text("risk_tier", self.risk_tier))
        object.__setattr__(self, "confidence", _validate_confidence_score("confidence", self.confidence))
        object.__setattr__(self, "notes", _normalize_string_tuple("notes", self.notes))
        object.__setattr__(self, "provenance", _normalize_provenance(self.provenance))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DecisionPacket:
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True)
class Observation(ContractModel):
    """Structured learned statement backed by captured episodes."""

    KIND_VALUES: ClassVar[tuple[str, ...]] = (
        "pattern",
        "preference",
        "anti_pattern",
        "workflow",
        "constraint",
        "failure_mode",
    )
    CONFIDENCE_VALUES: ClassVar[tuple[str, ...]] = ("low", "medium", "high")
    STATUS_VALUES: ClassVar[tuple[str, ...]] = ("active", "superseded", "rejected")

    observation_id: str
    episode_ids: tuple[str, ...]
    kind: ObservationKind
    statement: str
    confidence: ConfidenceLevel
    status: ObservationStatus
    supporting_evidence: tuple[str, ...] = ()
    applies_to: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    superseded_by: str | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _validate_required_text("observation_id", self.observation_id))
        object.__setattr__(
            self,
            "episode_ids",
            _normalize_string_tuple("episode_ids", self.episode_ids, require_non_empty=True),
        )
        object.__setattr__(self, "kind", _validate_literal("kind", self.kind, self.KIND_VALUES))
        object.__setattr__(self, "statement", _validate_required_text("statement", self.statement))
        object.__setattr__(
            self,
            "confidence",
            _validate_literal("confidence", self.confidence, self.CONFIDENCE_VALUES),
        )
        object.__setattr__(self, "status", _validate_literal("status", self.status, self.STATUS_VALUES))
        object.__setattr__(
            self,
            "supporting_evidence",
            _normalize_string_tuple("supporting_evidence", self.supporting_evidence),
        )
        object.__setattr__(self, "applies_to", _normalize_string_tuple("applies_to", self.applies_to))
        object.__setattr__(self, "tags", _normalize_string_tuple("tags", self.tags))
        object.__setattr__(self, "superseded_by", _validate_optional_text("superseded_by", self.superseded_by))
        object.__setattr__(self, "provenance", _normalize_provenance(self.provenance))
        if self.status == "superseded" and self.superseded_by is None:
            raise ContractValidationError("superseded observations must set superseded_by")
        if self.status != "superseded" and self.superseded_by is not None:
            raise ContractValidationError("superseded_by is only valid when status='superseded'")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Observation:
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True)
class CandidateArtifact(ContractModel):
    """Candidate-only artifact record for OpenSpace and distillation outputs."""

    STATUS_VALUES: ClassVar[tuple[str, ...]] = (
        "draft",
        "under_evaluation",
        "held",
        "rejected",
        "promoted",
    )
    SOURCE_VALUES: ClassVar[tuple[str, ...]] = ("bridge", "openspace", "distillation", "manual")
    ARTIFACT_VALUES: ClassVar[tuple[str, ...]] = tuple(CANDIDATE_DIR_BY_ARTIFACT_TYPE.keys())

    candidate_id: str
    artifact_type: ArtifactType
    source: CandidateSource
    candidate_path: str
    intended_target: str
    status: CandidateStatus
    decision_packet_id: str | None = None
    provenance: Provenance | None = None
    eval_pack: Mapping[str, FrozenJSONValue] | None = None
    risk_tier: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _validate_required_text("candidate_id", self.candidate_id))
        artifact_type = _validate_literal("artifact_type", self.artifact_type, self.ARTIFACT_VALUES)
        object.__setattr__(self, "artifact_type", artifact_type)
        object.__setattr__(self, "source", _validate_literal("source", self.source, self.SOURCE_VALUES))
        object.__setattr__(self, "candidate_path", _validate_candidate_path(artifact_type, self.candidate_path))
        object.__setattr__(self, "intended_target", _validate_required_text("intended_target", self.intended_target))
        object.__setattr__(self, "status", _validate_literal("status", self.status, self.STATUS_VALUES))
        object.__setattr__(
            self,
            "decision_packet_id",
            _validate_optional_text("decision_packet_id", self.decision_packet_id),
        )
        provenance = _normalize_provenance(self.provenance)
        if (
            provenance is not None
            and self.decision_packet_id is not None
            and provenance.decision_packet_ids
            and self.decision_packet_id not in provenance.decision_packet_ids
        ):
            raise ContractValidationError(
                "decision_packet_id must match provenance.decision_packet_ids when both are provided"
            )
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "eval_pack", _normalize_mapping("eval_pack", self.eval_pack, allow_none=True))
        object.__setattr__(self, "risk_tier", _validate_optional_text("risk_tier", self.risk_tier))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CandidateArtifact:
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True)
class PromotionDecision(ContractModel):
    """Append-only selfbuild decision ledger entry."""

    OUTCOME_VALUES: ClassVar[tuple[str, ...]] = ("promoted", "held", "rejected", "archived")

    decision_id: str
    candidate_id: str
    outcome: PromotionOutcome
    timestamp: str
    reasons: tuple[str, ...]
    replay_results: Mapping[str, FrozenJSONValue] | None = None
    benchmark_results: Mapping[str, FrozenJSONValue] | None = None
    regression_report: Mapping[str, FrozenJSONValue] | None = None
    promoted_to: str | None = None
    approver: str | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _validate_required_text("decision_id", self.decision_id))
        object.__setattr__(self, "candidate_id", _validate_required_text("candidate_id", self.candidate_id))
        object.__setattr__(self, "outcome", _validate_literal("outcome", self.outcome, self.OUTCOME_VALUES))
        object.__setattr__(self, "timestamp", _validate_iso_timestamp("timestamp", self.timestamp))
        object.__setattr__(self, "reasons", _normalize_string_tuple("reasons", self.reasons, require_non_empty=True))
        object.__setattr__(
            self,
            "replay_results",
            _normalize_mapping("replay_results", self.replay_results, allow_none=True),
        )
        object.__setattr__(
            self,
            "benchmark_results",
            _normalize_mapping("benchmark_results", self.benchmark_results, allow_none=True),
        )
        object.__setattr__(
            self,
            "regression_report",
            _normalize_mapping("regression_report", self.regression_report, allow_none=True),
        )
        object.__setattr__(self, "promoted_to", _validate_optional_text("promoted_to", self.promoted_to))
        object.__setattr__(self, "approver", _validate_optional_text("approver", self.approver))
        object.__setattr__(self, "provenance", _normalize_provenance(self.provenance))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PromotionDecision:
        return cls(**dict(payload))


ArchitectureContract: TypeAlias = (
    BuildCaptureEvent | DecisionPacket | Observation | CandidateArtifact | PromotionDecision
)


def serialize_contract(record: Provenance | ArchitectureContract) -> dict[str, JSONValue]:
    """Return a JSON-safe dictionary for a canonical contract record."""

    if not is_dataclass(record):
        raise TypeError("serialize_contract expects a dataclass contract instance")
    payload: dict[str, JSONValue] = {}
    for field_info in fields(record):
        value = _thaw_json(getattr(record, field_info.name))
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        payload[field_info.name] = value
    return payload


__all__ = [
    "ArchitectureContract",
    "ArtifactType",
    "BuildCaptureEvent",
    "CANDIDATE_DIR_BY_ARTIFACT_TYPE",
    "CandidateArtifact",
    "CandidateSource",
    "CandidateStatus",
    "ConfidenceLevel",
    "ContextType",
    "ContractValidationError",
    "DecisionPacket",
    "DecisionPacketStatus",
    "EventStatus",
    "EventType",
    "EvidenceSource",
    "JSONValue",
    "Observation",
    "ObservationKind",
    "ObservationStatus",
    "PromotionDecision",
    "PromotionOutcome",
    "Provenance",
    "serialize_contract",
]
