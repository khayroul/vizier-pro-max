"""Tests for bridge/watcher.py — bridge entry point."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bridge import watcher
from bridge.watcher import _load_state, _save_state, run


class TestLoadState:
    def test_returns_default_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / ".vizier-pro-max" / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == {"manifests": {}, "pipelines": {}}

    def test_loads_existing_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        state_data = {"manifests": {"foo.yaml": 1000.0}, "pipelines": {"bar": 2000.0}}
        state_file.write_text(json.dumps(state_data), encoding="utf-8")
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == state_data

    def test_returns_default_on_invalid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        state_file.write_text("not valid json {{{{", encoding="utf-8")
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == {"manifests": {}, "pipelines": {}}

    def test_returns_default_on_os_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        # Create a directory at the path so read fails
        state_file.mkdir()
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == {"manifests": {}, "pipelines": {}}


class TestSaveState:
    def test_persists_to_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "subdir" / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = {"manifests": {"foo": 1.0}, "pipelines": {}}
        _save_state(state)

        assert state_file.exists()
        loaded = json.loads(state_file.read_text(encoding="utf-8"))
        assert loaded == state

    def test_creates_parent_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "a" / "b" / "c" / "state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        _save_state({"manifests": {}, "pipelines": {}})
        assert state_file.exists()


class TestStateRoundtrip:
    def test_save_and_load_roundtrip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        original = {
            "manifests": {"path/to/tool.yaml": 12345.6},
            "pipelines": {"my_pipeline": 99999.0},
        }
        _save_state(original)
        loaded = _load_state()
        assert loaded == original


class TestRun:
    @patch("bridge.watcher.manifest_syncer")
    def test_run_calls_manifest_syncer(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        mock_syncer.check_new_manifests.return_value = ([], {})
        mock_syncer.check_new_pipelines.return_value = ([], {})

        manifests_dir = tmp_path / "manifests"
        pipelines_dir = tmp_path / "pipelines"
        manifests_dir.mkdir()
        pipelines_dir.mkdir()

        with patch("bridge.git_watcher.run") as mock_git_run:
            mock_git_run.return_value = None
            run(repo_path=tmp_path)

        mock_syncer.check_new_manifests.assert_called_once()
        mock_syncer.check_new_pipelines.assert_called_once()

    @patch("bridge.watcher.manifest_syncer")
    def test_run_saves_state_after_execution(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        mock_syncer.check_new_manifests.return_value = (["tool_a"], {})
        mock_syncer.check_new_pipelines.return_value = ([], {})

        (tmp_path / "manifests").mkdir()
        (tmp_path / "pipelines").mkdir()

        with patch("bridge.git_watcher.run") as mock_git_run:
            mock_git_run.return_value = None
            run(repo_path=tmp_path)

        assert state_file.exists()

    @patch("bridge.watcher.manifest_syncer")
    def test_run_continues_when_git_watcher_fails(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        mock_syncer.check_new_manifests.return_value = ([], {})
        mock_syncer.check_new_pipelines.return_value = ([], {})

        (tmp_path / "manifests").mkdir()
        (tmp_path / "pipelines").mkdir()

        with patch("bridge.git_watcher.run") as mock_git_run:
            mock_git_run.side_effect = OSError("git exploded")
            # Should not raise
            run(repo_path=tmp_path)

        mock_syncer.check_new_manifests.assert_called_once()

    @patch("bridge.watcher.manifest_syncer")
    def test_run_uses_default_repo_path(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        mock_syncer.check_new_manifests.return_value = ([], {})
        mock_syncer.check_new_pipelines.return_value = ([], {})

        # Call run() without repo_path — should resolve from __file__ without error
        with patch("bridge.git_watcher.run"):
            run()  # No exception expected

    @patch("bridge.watcher.manifest_syncer")
    def test_run_skips_skill_syncer_when_no_skills_dir(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        mock_syncer.check_new_manifests.return_value = ([], {})
        mock_syncer.check_new_pipelines.return_value = ([], {})

        # No skills/ subdir — skill_syncer.sync_* should not be called
        (tmp_path / "manifests").mkdir()
        (tmp_path / "pipelines").mkdir()

        with patch("bridge.git_watcher.run"):
            with patch("bridge.skill_syncer") as mock_skill:
                run(repo_path=tmp_path)
                # sync functions should NOT be called because skills dir doesn't exist
                mock_skill.sync_repo_to_hermes.assert_not_called()
