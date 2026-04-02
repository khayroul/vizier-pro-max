"""Tests for the canonical v6.2 state layout helpers."""
from __future__ import annotations

from pathlib import Path

from augments.observational.store import (
    candidate_dir_for_artifact,
    ensure_state_layout,
    state_layout,
)


def test_state_layout_matches_documented_paths(tmp_path: Path) -> None:
    layout = state_layout(tmp_path / "state")

    assert layout.build_capture_events == tmp_path / "state" / "build_capture" / "events.jsonl"
    assert layout.build_capture_index_db == tmp_path / "state" / "build_capture" / "index.sqlite"
    assert layout.observational_episodes_db == tmp_path / "state" / "observational" / "episodes.sqlite"
    assert layout.observational_observations_db == tmp_path / "state" / "observational" / "observations.sqlite"
    assert layout.observational_reflections_db == tmp_path / "state" / "observational" / "reflections.sqlite"
    assert layout.selfbuild_decisions == tmp_path / "state" / "selfbuild" / "decisions.jsonl"
    assert layout.distillation_approved_traces_dir == tmp_path / "state" / "distillation" / "approved_traces"


def test_ensure_state_layout_creates_directories_but_not_files(tmp_path: Path) -> None:
    layout = ensure_state_layout(tmp_path / "state")

    for directory in layout.directories():
        assert directory.is_dir()

    for file_path in layout.files():
        assert not file_path.exists()


def test_candidate_dir_for_artifact_uses_canonical_family_mapping(tmp_path: Path) -> None:
    assert candidate_dir_for_artifact("skill", tmp_path / "state") == tmp_path / "state" / "candidates" / "skills"
    assert (
        candidate_dir_for_artifact("distillation_program", tmp_path / "state")
        == tmp_path / "state" / "candidates" / "distillation"
    )
