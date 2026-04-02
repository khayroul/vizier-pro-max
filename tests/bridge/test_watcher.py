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
        assert state == {
            "manifests": {},
            "pipelines": {},
            "runtime_capture": {"last_prompt_log_id": 0.0},
        }

    def test_loads_existing_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        state_data = {"manifests": {"foo.yaml": 1000.0}, "pipelines": {"bar": 2000.0}}
        state_file.write_text(json.dumps(state_data), encoding="utf-8")
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == {
            "manifests": {"foo.yaml": 1000.0},
            "pipelines": {"bar": 2000.0},
            "runtime_capture": {"last_prompt_log_id": 0.0},
        }

    def test_returns_default_on_invalid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        state_file.write_text("not valid json {{{{", encoding="utf-8")
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == {
            "manifests": {},
            "pipelines": {},
            "runtime_capture": {"last_prompt_log_id": 0.0},
        }

    def test_returns_default_on_os_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        # Create a directory at the path so read fails
        state_file.mkdir()
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        state = _load_state()
        assert state == {
            "manifests": {},
            "pipelines": {},
            "runtime_capture": {"last_prompt_log_id": 0.0},
        }


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
            "runtime_capture": {"last_prompt_log_id": 8.0},
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
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                mock_git_run.return_value = None
                mock_session_sync.return_value = MagicMock(last_prompt_log_id=0)
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
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                mock_git_run.return_value = None
                mock_session_sync.return_value = MagicMock(last_prompt_log_id=4)
                run(repo_path=tmp_path)

        assert state_file.exists()
        loaded = json.loads(state_file.read_text(encoding="utf-8"))
        assert loaded["runtime_capture"] == {"last_prompt_log_id": 4.0}

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
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                mock_git_run.side_effect = OSError("git exploded")
                mock_session_sync.return_value = MagicMock(last_prompt_log_id=0)
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
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                mock_session_sync.return_value = MagicMock(last_prompt_log_id=0)
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
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                with patch("bridge.skill_syncer") as mock_skill:
                    mock_session_sync.return_value = MagicMock(last_prompt_log_id=0)
                    run(repo_path=tmp_path)
                    # sync functions should NOT be called because skills dir doesn't exist
                    mock_skill.sync_repo_to_hermes.assert_not_called()

    @patch("bridge.watcher.manifest_syncer")
    def test_run_emits_capture_events_for_detected_changes(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        manifest_path = tmp_path / "manifests" / "code" / "tool.yaml"
        pipeline_path = tmp_path / "pipelines" / "build.py"
        manifest_path.parent.mkdir(parents=True)
        pipeline_path.parent.mkdir(parents=True)

        mock_syncer.check_new_manifests.return_value = (
            ["tool-name"],
            {str(manifest_path): 1234.0},
        )
        mock_syncer.check_new_pipelines.return_value = (
            ["build"],
            {str(pipeline_path): 5678.0},
        )

        with patch("bridge.git_watcher.run"):
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                with patch("bridge.watcher.capture_external_build_event") as mock_capture:
                    mock_session_sync.return_value = MagicMock(last_prompt_log_id=0)
                    run(repo_path=tmp_path)

        assert mock_capture.call_count == 2
        manifest_call = mock_capture.call_args_list[0].kwargs
        pipeline_call = mock_capture.call_args_list[1].kwargs
        assert manifest_call["event_type"] == "artifact_created"
        assert manifest_call["files_touched"] == ("manifests/code/tool.yaml",)
        assert manifest_call["artifacts"] == ("tool-name",)
        assert pipeline_call["event_type"] == "file_changed"
        assert pipeline_call["files_touched"] == ("pipelines/build.py",)

    @patch("bridge.watcher.manifest_syncer")
    def test_run_syncs_runtime_capture_before_saving_state(
        self, mock_syncer: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "bridge-state.json"
        monkeypatch.setattr(watcher, "_STATE_FILE", state_file)

        mock_syncer.check_new_manifests.return_value = ([], {})
        mock_syncer.check_new_pipelines.return_value = ([], {})

        (tmp_path / "manifests").mkdir()
        (tmp_path / "pipelines").mkdir()

        with patch("bridge.git_watcher.run"):
            with patch("bridge.watcher.sync_prompt_log_to_build_capture") as mock_session_sync:
                mock_session_sync.return_value = MagicMock(last_prompt_log_id=11)
                run(repo_path=tmp_path)

        mock_session_sync.assert_called_once_with(
            state_root=tmp_path / "state",
            after_row_id=0,
        )
