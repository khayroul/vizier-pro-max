"""Packet-scoped helpers for the canonical v6.2 state layout."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from augments.observational.types import ArtifactType, CANDIDATE_DIR_BY_ARTIFACT_TYPE

DEFAULT_STATE_ROOT = Path("state")


@dataclass(frozen=True, slots=True)
class StateLayout:
    """Resolved path surface for the shared runtime state tree."""

    root: Path
    build_capture_dir: Path
    build_capture_events: Path
    build_capture_index_db: Path
    observational_dir: Path
    observational_episodes_db: Path
    observational_observations_db: Path
    observational_reflections_db: Path
    candidates_dir: Path
    candidate_skills_dir: Path
    candidate_prompts_dir: Path
    candidate_templates_dir: Path
    candidate_pipelines_dir: Path
    candidate_routing_dir: Path
    candidate_distillation_dir: Path
    selfbuild_dir: Path
    selfbuild_decisions: Path
    selfbuild_replay_dir: Path
    selfbuild_benchmarks_dir: Path
    distillation_dir: Path
    distillation_approved_traces_dir: Path
    distillation_evaluations_dir: Path

    def directories(self) -> tuple[Path, ...]:
        """Return every canonical directory in deterministic order."""

        return (
            self.root,
            self.build_capture_dir,
            self.observational_dir,
            self.candidates_dir,
            self.candidate_skills_dir,
            self.candidate_prompts_dir,
            self.candidate_templates_dir,
            self.candidate_pipelines_dir,
            self.candidate_routing_dir,
            self.candidate_distillation_dir,
            self.selfbuild_dir,
            self.selfbuild_replay_dir,
            self.selfbuild_benchmarks_dir,
            self.distillation_dir,
            self.distillation_approved_traces_dir,
            self.distillation_evaluations_dir,
        )

    def files(self) -> tuple[Path, ...]:
        """Return the canonical ledger and SQLite file locations."""

        return (
            self.build_capture_events,
            self.build_capture_index_db,
            self.observational_episodes_db,
            self.observational_observations_db,
            self.observational_reflections_db,
            self.selfbuild_decisions,
        )

    def candidate_dir(self, artifact_type: ArtifactType) -> Path:
        """Resolve the canonical candidate directory for an artifact type."""

        return self.candidates_dir / CANDIDATE_DIR_BY_ARTIFACT_TYPE[artifact_type]


def state_layout(root: Path | str = DEFAULT_STATE_ROOT) -> StateLayout:
    """Resolve the shared v6.2 state layout without touching the filesystem."""

    state_root = Path(root)
    build_capture_dir = state_root / "build_capture"
    observational_dir = state_root / "observational"
    candidates_dir = state_root / "candidates"
    selfbuild_dir = state_root / "selfbuild"
    distillation_dir = state_root / "distillation"

    return StateLayout(
        root=state_root,
        build_capture_dir=build_capture_dir,
        build_capture_events=build_capture_dir / "events.jsonl",
        build_capture_index_db=build_capture_dir / "index.sqlite",
        observational_dir=observational_dir,
        observational_episodes_db=observational_dir / "episodes.sqlite",
        observational_observations_db=observational_dir / "observations.sqlite",
        observational_reflections_db=observational_dir / "reflections.sqlite",
        candidates_dir=candidates_dir,
        candidate_skills_dir=candidates_dir / "skills",
        candidate_prompts_dir=candidates_dir / "prompts",
        candidate_templates_dir=candidates_dir / "templates",
        candidate_pipelines_dir=candidates_dir / "pipelines",
        candidate_routing_dir=candidates_dir / "routing",
        candidate_distillation_dir=candidates_dir / "distillation",
        selfbuild_dir=selfbuild_dir,
        selfbuild_decisions=selfbuild_dir / "decisions.jsonl",
        selfbuild_replay_dir=selfbuild_dir / "replay",
        selfbuild_benchmarks_dir=selfbuild_dir / "benchmarks",
        distillation_dir=distillation_dir,
        distillation_approved_traces_dir=distillation_dir / "approved_traces",
        distillation_evaluations_dir=distillation_dir / "evaluations",
    )


def ensure_state_layout(root: Path | str = DEFAULT_STATE_ROOT) -> StateLayout:
    """Create the canonical directories while leaving append-first files absent."""

    layout = state_layout(root)
    for directory in layout.directories():
        directory.mkdir(parents=True, exist_ok=True)
    return layout


def candidate_dir_for_artifact(
    artifact_type: ArtifactType,
    root: Path | str = DEFAULT_STATE_ROOT,
) -> Path:
    """Resolve the canonical candidate directory for a packet artifact type."""

    return state_layout(root).candidate_dir(artifact_type)


__all__ = [
    "DEFAULT_STATE_ROOT",
    "StateLayout",
    "candidate_dir_for_artifact",
    "ensure_state_layout",
    "state_layout",
]
