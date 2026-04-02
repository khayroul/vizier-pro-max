"""Tests for wiring _start_hermes_session to real Hermes CLI invocation."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.triggers.data_trigger import _start_hermes_session, process_file


class TestStartHermesSession:
    """Test _start_hermes_session with dry_run and real invocation paths."""

    def test_dry_run_logs_instead_of_executing(self, tmp_path: Path) -> None:
        """dry_run=True should log but NOT call subprocess."""
        dummy_file = tmp_path / "test.csv"
        dummy_file.write_text("a,b\n1,2\n")

        with patch("scripts.triggers.data_trigger.subprocess") as mock_sub:
            _start_hermes_session(
                toolset="vizier-visual",
                pipeline="poster_batch",
                file_path=dummy_file,
                schema={"a": "string"},
                dry_run=True,
            )
            mock_sub.run.assert_not_called()

    def test_real_invocation_calls_subprocess(self, tmp_path: Path) -> None:
        """dry_run=False should call subprocess.run with Hermes command."""
        dummy_file = tmp_path / "test.csv"
        dummy_file.write_text("a,b\n1,2\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Session complete"
        mock_result.stderr = ""

        with patch("scripts.triggers.data_trigger.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            mock_sub.PIPE = subprocess.PIPE
            _start_hermes_session(
                toolset="vizier-visual",
                pipeline="poster_batch",
                file_path=dummy_file,
                schema={"a": "string"},
                dry_run=False,
            )
            mock_sub.run.assert_called_once()
            call_args = mock_sub.run.call_args
            cmd = call_args[0][0]
            # Should contain hermes invocation
            assert "hermes-agent" in " ".join(cmd) or "run_agent" in " ".join(cmd)

    def test_real_invocation_includes_toolset(self, tmp_path: Path) -> None:
        """The subprocess command should include --enabled_toolsets."""
        dummy_file = tmp_path / "test.csv"
        dummy_file.write_text("a,b\n1,2\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("scripts.triggers.data_trigger.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            mock_sub.PIPE = subprocess.PIPE
            _start_hermes_session(
                toolset="vizier-analytics",
                pipeline=None,
                file_path=dummy_file,
                schema={"x": "int"},
                dry_run=False,
            )
            cmd = mock_sub.run.call_args[0][0]
            cmd_str = " ".join(cmd)
            assert "vizier-analytics" in cmd_str

    def test_subprocess_failure_raises(self, tmp_path: Path) -> None:
        """Non-zero exit code should raise RuntimeError."""
        dummy_file = tmp_path / "test.csv"
        dummy_file.write_text("a,b\n1,2\n")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "model not found"

        with patch("scripts.triggers.data_trigger.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            mock_sub.PIPE = subprocess.PIPE
            with pytest.raises(RuntimeError, match="Hermes session failed"):
                _start_hermes_session(
                    toolset="vizier-visual",
                    pipeline=None,
                    file_path=dummy_file,
                    schema={},
                    dry_run=False,
                )


class TestProcessFileDryRun:
    """Verify process_file threads dry_run correctly."""

    def test_process_file_dry_run_succeeds(self, tmp_path: Path) -> None:
        """process_file with dry_run=True should succeed without subprocess."""
        uploads = tmp_path / "uploads"
        uploads.mkdir()
        csv_file = uploads / "posters_test.csv"
        csv_file.write_text("title,color\nSpring,red\n")

        result = process_file(csv_file, uploads, dry_run=True)
        assert result.status == "processed"
        assert result.toolset == "vizier-visual"
