"""Tests for git watcher — commit detection and MEMORY.md writing."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bridge import git_watcher
from bridge.git_watcher import (
    _load_state,
    _save_state,
    _split_entries,
    detect_new_commits,
    extract_changes,
    format_memory_entry,
    update_memory_md,
)


def _init_repo(tmp_path: Path) -> Path:
    """Create a temp git repo with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Claude Code"], cwd=repo, capture_output=True
    )
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
        subprocess.run(
            ["git", "commit", "-m", "feat: add bar"], cwd=repo, capture_output=True
        )

        commits = detect_new_commits(base_sha, repo)
        assert len(commits) == 1
        assert "feat: add bar" in commits[0]["subject"]

    def test_skips_aider_commits(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "config", "user.name", "aider"], cwd=repo, capture_output=True
        )
        (repo / "vizier" / "bar.py").write_text("def bar(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "aider change"], cwd=repo, capture_output=True
        )

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
        # Rolled off (exact heading to avoid substring match)
        assert "### Entry 4\n" not in content

    def test_creates_memory_file_when_missing(self, tmp_path: Path) -> None:
        memory = tmp_path / "MEMORY.md"
        assert not memory.exists()

        entry = "### 2026-04-01 00:00 — Dev\n- Created `foo.py`\n"
        update_memory_md(memory, entry)

        assert memory.exists()
        content = memory.read_text()
        assert "## Git Activity" in content
        assert "Created `foo.py`" in content

    def test_prepends_entry_to_existing_section(self, tmp_path: Path) -> None:
        memory = tmp_path / "MEMORY.md"
        memory.write_text(
            "# Hermes Memory\n\n## Git Activity\n\n### Old entry\n- Old change\n"
        )

        entry = "### New entry\n- New change\n"
        update_memory_md(memory, entry)

        content = memory.read_text()
        new_pos = content.find("### New entry")
        old_pos = content.find("### Old entry")
        assert new_pos < old_pos


class TestExtractChanges:
    def test_detects_added_and_modified_files(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()

        (repo / "vizier" / "new_file.py").write_text("x = 1\n")
        (repo / "vizier" / "foo.py").write_text(
            "def hello(): pass\ndef extra(): pass\n"
        )
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add and modify"], cwd=repo, capture_output=True
        )

        changes = extract_changes(base_sha, repo)
        assert "vizier/new_file.py" in changes["files_added"]
        assert "vizier/foo.py" in changes["files_modified"]

    def test_detects_deleted_files(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()

        (repo / "vizier" / "foo.py").unlink()
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "delete foo"], cwd=repo, capture_output=True
        )

        changes = extract_changes(base_sha, repo)
        assert "vizier/foo.py" in changes["files_deleted"]

    def test_returns_empty_on_git_error(self, tmp_path: Path) -> None:
        # tmp_path exists but is not a git repo — git diff will fail
        changes = extract_changes("abc123", tmp_path)
        assert changes["files_modified"] == []
        assert changes["files_added"] == []


class TestFormatMemoryEntry:
    def test_includes_all_sections(self) -> None:
        commits = [{"sha": "abc1234", "subject": "feat: add thing", "author": "Alice"}]
        changes = {
            "files_modified": ["foo.py"],
            "files_added": ["bar.py"],
            "files_deleted": ["old.py"],
            "functions_added": ["new_func"],
            "functions_removed": ["old_func"],
            "classes_added": ["MyClass"],
            "classes_removed": ["OldClass"],
        }
        entry = format_memory_entry(commits, changes)

        assert "### " in entry
        assert "Alice" in entry
        assert "Modified `foo.py`" in entry
        assert "Created `bar.py`" in entry
        assert "Deleted `old.py`" in entry
        assert "new_func" in entry
        assert "old_func" in entry
        assert "MyClass" in entry
        assert "OldClass" in entry
        assert "abc1234"[:7] in entry

    def test_empty_changes_produces_minimal_entry(self) -> None:
        commits = [{"sha": "deadbeef", "subject": "chore: clean up", "author": "Bob"}]
        changes: dict[str, list[str]] = {
            "files_modified": [],
            "files_added": [],
            "files_deleted": [],
            "functions_added": [],
            "functions_removed": [],
            "classes_added": [],
            "classes_removed": [],
        }
        entry = format_memory_entry(commits, changes)
        assert "Bob" in entry
        assert "deadbeef"[:7] in entry

    def test_multiple_authors_sorted(self) -> None:
        commits = [
            {"sha": "aaa0000", "subject": "feat: a", "author": "Zara"},
            {"sha": "bbb0000", "subject": "feat: b", "author": "Alice"},
        ]
        entry = format_memory_entry(commits, {})
        alice_pos = entry.find("Alice")
        zara_pos = entry.find("Zara")
        assert alice_pos < zara_pos  # sorted alphabetically


class TestSplitEntries:
    def test_splits_on_triple_hash(self) -> None:
        body = "\n### Entry A\n- foo\n### Entry B\n- bar\n"
        entries = _split_entries(body)
        assert len(entries) == 2
        assert entries[0].startswith("### Entry A")
        assert entries[1].startswith("### Entry B")

    def test_empty_body_returns_empty_list(self) -> None:
        entries = _split_entries("")
        assert entries == []

    def test_no_entries_returns_empty(self) -> None:
        entries = _split_entries("\nsome text without hash headers\n")
        assert entries == []


class TestLoadSaveState:
    def test_returns_empty_dict_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "watcher-state.json"
        monkeypatch.setattr(git_watcher, "_STATE_FILE", state_file)
        assert _load_state() == {}

    def test_returns_empty_dict_on_bad_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "watcher-state.json"
        state_file.write_text("{{bad json}}", encoding="utf-8")
        monkeypatch.setattr(git_watcher, "_STATE_FILE", state_file)
        assert _load_state() == {}

    def test_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        state_file = tmp_path / "watcher-state.json"
        monkeypatch.setattr(git_watcher, "_STATE_FILE", state_file)

        original = {"last_sha": "abc123", "last_run": "2026-04-01T00:00:00+00:00"}
        _save_state(original)
        loaded = _load_state()
        assert loaded == original


class TestDetectNewCommitsEdgeCases:
    def test_returns_empty_on_git_failure(self, tmp_path: Path) -> None:
        # tmp_path exists but is not a git repo — git log will fail
        commits = detect_new_commits("abc123", tmp_path)
        assert commits == []

    def test_handles_empty_output(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        # No commits after HEAD -> empty list
        commits = detect_new_commits(head, repo)
        assert commits == []


class TestRunGitWatcher:
    def test_first_run_records_head_and_returns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        state_file = tmp_path / "watcher-state.json"
        monkeypatch.setattr(git_watcher, "_STATE_FILE", state_file)

        git_watcher.run(repo_path=repo)

        # Should have saved last_sha
        state = json.loads(state_file.read_text())
        assert "last_sha" in state
        assert len(state["last_sha"]) == 40

    def test_second_run_with_no_new_commits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        state_file = tmp_path / "watcher-state.json"
        monkeypatch.setattr(git_watcher, "_STATE_FILE", state_file)

        # First run — bootstraps state
        git_watcher.run(repo_path=repo)

        # Second run — no new commits, should just update last_run
        git_watcher.run(repo_path=repo)
        state = json.loads(state_file.read_text())
        assert "last_run" in state

    def test_run_with_new_commit_and_no_memory_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        state_file = tmp_path / "watcher-state.json"
        monkeypatch.setattr(git_watcher, "_STATE_FILE", state_file)

        # Bootstrap
        git_watcher.run(repo_path=repo)

        # Add a new commit
        (repo / "vizier" / "new.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: new file"], cwd=repo, capture_output=True
        )

        # MEMORY.md doesn't exist — should log a warning but not crash
        git_watcher.run(repo_path=repo)
        state = json.loads(state_file.read_text())
        assert "last_sha" in state
