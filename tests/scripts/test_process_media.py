"""Tests for ffmpeg_process wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestProcessMedia:
    def test_convert_format(self, tmp_path: Path) -> None:
        from scripts.audio.process_media import run

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"RIFF" + b"\x00" * 40)  # fake WAV header
        output = tmp_path / "output.mp3"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = run(
                input_path=str(input_file),
                output_path=str(output),
                operation="convert",
            )
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]

    def test_trim(self, tmp_path: Path) -> None:
        from scripts.audio.process_media import run

        input_file = tmp_path / "input.mp3"
        input_file.write_bytes(b"\x00" * 100)
        output = tmp_path / "trimmed.mp3"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            run(
                input_path=str(input_file),
                output_path=str(output),
                operation="trim",
                start_time="00:00:05",
                end_time="00:00:30",
            )
        cmd = mock_run.call_args[0][0]
        assert "-ss" in cmd
        assert "00:00:05" in cmd

    def test_unknown_operation_raises(self, tmp_path: Path) -> None:
        from scripts.audio.process_media import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(
                input_path=str(tmp_path / "in.mp3"),
                output_path=str(tmp_path / "out.mp3"),
                operation="reverse",
            )
