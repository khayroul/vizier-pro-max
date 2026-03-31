"""Tests for bi-directional skill syncer."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from bridge.skill_syncer import sync_hermes_to_repo, sync_repo_to_hermes


@pytest.fixture()
def repo_skills(tmp_path: Path) -> Path:
    """Create a temporary repo skills directory."""
    skills = tmp_path / "repo_skills"
    skills.mkdir()
    return skills


@pytest.fixture()
def hermes_skills(tmp_path: Path) -> Path:
    """Create a temporary Hermes skills directory."""
    skills = tmp_path / "hermes_skills"
    skills.mkdir()
    return skills


def _write_skill(directory: Path, name: str, content: str) -> Path:
    """Write a SKILL.md into a named skill directory."""
    skill_dir = directory / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content)
    return skill_file


class TestSyncRepoToHermes:
    """Tests for sync_repo_to_hermes."""

    def test_copies_new_skill(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """New repo skill is copied to Hermes."""
        _write_skill(repo_skills, "summarize", "# Summarize\nDo stuff")

        count = sync_repo_to_hermes(repo_skills, hermes_skills)

        assert count == 1
        target = hermes_skills / "summarize" / "SKILL.md"
        assert target.exists()
        assert target.read_text() == "# Summarize\nDo stuff"

    def test_overwrites_older_hermes_skill(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """Repo skill with newer mtime overwrites older Hermes copy."""
        hermes_file = _write_skill(hermes_skills, "translate", "old version")
        # Ensure the repo file is strictly newer
        time.sleep(0.05)
        _write_skill(repo_skills, "translate", "new version")

        count = sync_repo_to_hermes(repo_skills, hermes_skills)

        assert count == 1
        assert hermes_file.read_text() == "new version"

    def test_skips_when_hermes_is_newer(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """Do NOT overwrite when Hermes copy is newer."""
        _write_skill(repo_skills, "classify", "repo version")
        time.sleep(0.05)
        hermes_file = _write_skill(hermes_skills, "classify", "hermes version")

        count = sync_repo_to_hermes(repo_skills, hermes_skills)

        assert count == 0
        assert hermes_file.read_text() == "hermes version"

    def test_handles_empty_repo_dir(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """Empty repo directory results in zero synced skills."""
        count = sync_repo_to_hermes(repo_skills, hermes_skills)
        assert count == 0

    def test_handles_missing_repo_dir(
        self, tmp_path: Path, hermes_skills: Path
    ) -> None:
        """Missing repo directory results in zero synced skills."""
        missing = tmp_path / "does_not_exist"
        count = sync_repo_to_hermes(missing, hermes_skills)
        assert count == 0


class TestSyncHermesToRepo:
    """Tests for sync_hermes_to_repo."""

    def test_copies_new_hermes_skill(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """Hermes-created skill not in repo is copied over."""
        _write_skill(hermes_skills, "auto_debug", "# Auto Debug")

        count = sync_hermes_to_repo(hermes_skills, repo_skills)

        assert count == 1
        target = repo_skills / "auto_debug" / "SKILL.md"
        assert target.exists()
        assert target.read_text() == "# Auto Debug"

    def test_does_not_overwrite_existing_repo_skill(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """Existing repo skill is never overwritten by Hermes version."""
        repo_file = _write_skill(repo_skills, "summarize", "repo original")
        _write_skill(hermes_skills, "summarize", "hermes version")

        count = sync_hermes_to_repo(hermes_skills, repo_skills)

        assert count == 0
        assert repo_file.read_text() == "repo original"

    def test_handles_empty_hermes_dir(
        self, repo_skills: Path, hermes_skills: Path
    ) -> None:
        """Empty Hermes directory results in zero synced skills."""
        count = sync_hermes_to_repo(hermes_skills, repo_skills)
        assert count == 0

    def test_handles_missing_hermes_dir(
        self, tmp_path: Path, repo_skills: Path
    ) -> None:
        """Missing Hermes directory results in zero synced skills."""
        missing = tmp_path / "does_not_exist"
        count = sync_hermes_to_repo(missing, repo_skills)
        assert count == 0

    def test_creates_repo_dir_if_absent(
        self, tmp_path: Path, hermes_skills: Path
    ) -> None:
        """Repo skills directory is created if it doesn't exist."""
        repo = tmp_path / "new_repo_skills"
        _write_skill(hermes_skills, "new_skill", "# New")

        count = sync_hermes_to_repo(hermes_skills, repo)

        assert count == 1
        assert (repo / "new_skill" / "SKILL.md").exists()
