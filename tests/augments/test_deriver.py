"""Tests for OpenSpace deriver — promote better skill variants."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from augments.openspace.deriver import derive_skill
from augments.openspace.version_dag import SkillRecord, VersionDAG


@pytest.fixture()
def dag(tmp_path: Path) -> VersionDAG:
    return VersionDAG(db_path=tmp_path / "skills.db")


@pytest.fixture()
def base_skill(tmp_path: Path, dag: VersionDAG) -> SkillRecord:
    """Create a base skill with some usage stats."""
    skill_dir = tmp_path / "skills" / "poster"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Poster Skill\nGenerates posters.")
    record = SkillRecord(
        skill_id="poster__v0_bbb",
        name="poster",
        path=skill_dir,
        is_active=True,
        origin="CAPTURED",
        generation=0,
        parent_ids=(),
        change_summary="Initial capture",
        total_selections=10,
        total_completions=8,
    )
    dag.save(record)
    return record


class TestDeriver:
    def test_derive_creates_enhanced_version(
        self, dag: VersionDAG, base_skill: SkillRecord, tmp_path: Path
    ) -> None:
        """Derive creates a new enhanced version. Parent stays active (coexists)."""
        enhanced_content = "# Enhanced Poster Skill\nGenerates better posters with improved layout."

        with patch("augments.openspace.deriver._call_llm_for_enhancement", return_value=enhanced_content):
            result = derive_skill(
                dag=dag,
                skill_id="poster__v0_bbb",
                quality_scores={"poster__v0_bbb": 7.5},
                output_dir=tmp_path / "skills",
            )

        assert result is not None
        assert result.origin == "DERIVED"
        assert result.generation == 1
        assert "poster__v0_bbb" in result.parent_ids
        # Parent stays active (coexists with derived)
        assert dag.get("poster__v0_bbb").is_active is True
        # New version also active
        assert dag.get(result.skill_id).is_active is True

    def test_derive_skill_not_found(self, dag: VersionDAG, tmp_path: Path) -> None:
        """Derive returns None if skill doesn't exist."""
        result = derive_skill(
            dag=dag,
            skill_id="nonexistent__v0",
            quality_scores={},
            output_dir=tmp_path,
        )
        assert result is None

    def test_derive_writes_enhanced_skill_md(
        self, dag: VersionDAG, base_skill: SkillRecord, tmp_path: Path
    ) -> None:
        """Derive writes LLM-enhanced content to new directory."""
        enhanced = "# Super Poster\nAmazing poster generation."

        with patch("augments.openspace.deriver._call_llm_for_enhancement", return_value=enhanced):
            result = derive_skill(
                dag=dag,
                skill_id="poster__v0_bbb",
                quality_scores={"poster__v0_bbb": 8.0},
                output_dir=tmp_path / "skills",
            )

        assert result is not None
        new_skill_md = result.path / "SKILL.md"
        assert new_skill_md.exists()
        assert "Super Poster" in new_skill_md.read_text()
