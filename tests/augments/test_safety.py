"""Tests for OpenSpace skill safety validation."""
from __future__ import annotations

from pathlib import Path

from augments.openspace.safety import check_skill_safety


class TestSkillSafety:
    def test_safe_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "good_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Good Skill\nDoes good things.")
        assert check_skill_safety(skill_dir).is_safe is True

    def test_reject_shell_injection(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Run: `rm -rf /`")
        result = check_skill_safety(skill_dir)
        assert result.is_safe is False
        assert "shell" in result.reason.lower()

    def test_reject_oversized(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "huge_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("x" * 100_000)
        result = check_skill_safety(skill_dir)
        assert result.is_safe is False
        assert "size" in result.reason.lower()

    def test_reject_missing_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "empty_skill"
        skill_dir.mkdir()
        result = check_skill_safety(skill_dir)
        assert result.is_safe is False
