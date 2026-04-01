"""Tests for OpenSpace fixer — auto-repair broken skills from error logs."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from augments.openspace.fixer import fix_skill
from augments.openspace.version_dag import SkillRecord, VersionDAG


@pytest.fixture()
def dag(tmp_path: Path) -> VersionDAG:
    return VersionDAG(db_path=tmp_path / "skills.db")


@pytest.fixture()
def broken_skill(tmp_path: Path, dag: VersionDAG) -> SkillRecord:
    """Create a broken skill in the DAG and on disk."""
    skill_dir = tmp_path / "skills" / "broken_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Broken Skill\nThis skill has a bug.")
    record = SkillRecord(
        skill_id="broken__v0_aaa",
        name="broken",
        path=skill_dir,
        is_active=True,
        origin="CAPTURED",
        generation=0,
        parent_ids=(),
        change_summary="Initial capture",
    )
    dag.save(record)
    return record


class TestFixer:
    def test_fix_skill_creates_new_version(
        self, dag: VersionDAG, broken_skill: SkillRecord, tmp_path: Path
    ) -> None:
        """Fix creates a new version and deactivates the old one."""
        mock_llm_response = "# Fixed Skill\nThis skill is now working correctly."

        with patch("augments.openspace.fixer._call_llm_for_fix", return_value=mock_llm_response):
            result = fix_skill(
                dag=dag,
                skill_id="broken__v0_aaa",
                error_context="TypeError: unsupported operand",
                output_dir=tmp_path / "skills",
            )

        assert result is not None
        assert result.origin == "FIXED"
        assert result.generation == 1
        assert "broken__v0_aaa" in result.parent_ids
        # Old version deactivated
        assert dag.get("broken__v0_aaa").is_active is False
        # New version active
        assert dag.get(result.skill_id).is_active is True

    def test_fix_skill_not_found(self, dag: VersionDAG, tmp_path: Path) -> None:
        """Fix returns None if skill doesn't exist."""
        result = fix_skill(
            dag=dag,
            skill_id="nonexistent__v0",
            error_context="some error",
            output_dir=tmp_path,
        )
        assert result is None

    def test_fix_skill_writes_new_skill_md(
        self, dag: VersionDAG, broken_skill: SkillRecord, tmp_path: Path
    ) -> None:
        """Fix writes the LLM-generated content to a new SKILL.md."""
        fixed_content = "# Repaired Skill\nAll bugs resolved."

        with patch("augments.openspace.fixer._call_llm_for_fix", return_value=fixed_content):
            result = fix_skill(
                dag=dag,
                skill_id="broken__v0_aaa",
                error_context="KeyError: missing key",
                output_dir=tmp_path / "skills",
            )

        assert result is not None
        new_skill_md = result.path / "SKILL.md"
        assert new_skill_md.exists()
        assert "Repaired Skill" in new_skill_md.read_text()
