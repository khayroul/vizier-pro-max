"""Tests for git watcher — commit detection and MEMORY.md writing."""
from __future__ import annotations

import subprocess
from pathlib import Path

from bridge.git_watcher import (
    detect_new_commits,
    update_memory_md,
)


def _init_repo(tmp_path: Path) -> Path:
    """Create a temp git repo with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Claude Code"], cwd=repo, capture_output=True)
    (repo / "vizier").mkdir()
    (repo / "vizier" / "foo.py").write_text("def hello(): pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


class TestDetectNewCommits:
    def test_detects_new_commit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        ).stdout.strip()
        (repo / "vizier" / "bar.py").write_text("def bar(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: add bar"], cwd=repo, capture_output=True)

        commits = detect_new_commits(base_sha, repo)
        assert len(commits) == 1
        assert "feat: add bar" in commits[0]["subject"]

    def test_skips_aider_commits(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(["git", "config", "user.name", "aider"], cwd=repo, capture_output=True)
        (repo / "vizier" / "bar.py").write_text("def bar(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aider change"], cwd=repo, capture_output=True)

        commits = detect_new_commits(base_sha, repo)
        assert len(commits) == 0


class TestUpdateMemoryMd:
    def test_creates_git_activity_section(self, tmp_path: Path) -> None:
        memory = tmp_path / "MEMORY.md"
        memory.write_text("# Hermes Memory\n\n## System State\n\nSome state.\n")

        entry = "### 2026-03-31 10:15 — Claude Code\n- Modified `vizier/foo.py`\n"
        update_memory_md(memory, entry)

        content = memory.read_text()
        assert "## Git Activity" in content
        assert "Modified `vizier/foo.py`" in content
        assert "## System State" in content  # Preserved

    def test_rolling_window(self, tmp_path: Path) -> None:
        memory = tmp_path / "MEMORY.md"
        memory.write_text("# Hermes Memory\n")

        for i in range(55):
            entry = f"### Entry {i}\n- Change {i}\n"
            update_memory_md(memory, entry, max_entries=50)

        content = memory.read_text()
        assert "Entry 54" in content  # Newest
        assert "Entry 5" in content   # 50th from end
        assert "### Entry 4\n" not in content  # Rolled off (exact heading to avoid substring match)
