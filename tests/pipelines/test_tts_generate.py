"""Tests for tts_generate pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pipelines.tts_generate import run


class TestTtsGenerate:
    def test_generates_normalized_audio(self, tmp_path: Path) -> None:
        """Full pipeline: TTS -> normalize -> output."""
        output = str(tmp_path / "speech.mp3")

        with patch("pipelines.tts_generate.tts_run") as mock_tts, \
             patch("pipelines.tts_generate.ffmpeg_run") as mock_ffmpeg:
            mock_tts.return_value = {"file_path": str(tmp_path / "raw.mp3")}
            mock_ffmpeg.return_value = {"file_path": output}

            result = run(text="Hello world", output_path=output)

        assert result["status"] == "completed"
        assert result["file_path"] == output
        assert result["voice"] == "en-US-AriaNeural"
        mock_tts.assert_called_once()
        mock_ffmpeg.assert_called_once()

    def test_custom_voice(self, tmp_path: Path) -> None:
        """Custom voice parameter is passed through."""
        output = str(tmp_path / "speech.mp3")

        with patch("pipelines.tts_generate.tts_run") as mock_tts, \
             patch("pipelines.tts_generate.ffmpeg_run") as mock_ffmpeg:
            mock_tts.return_value = {"file_path": str(tmp_path / "raw.mp3")}
            mock_ffmpeg.return_value = {"file_path": output}

            result = run(text="Test", output_path=output, voice="ms-MY-YasminNeural")

        assert result["voice"] == "ms-MY-YasminNeural"
        mock_tts.assert_called_once_with(
            text="Test",
            output_path=mock_tts.call_args.kwargs["output_path"],
            voice="ms-MY-YasminNeural",
        )

    def test_empty_text_raises(self) -> None:
        """Empty text raises ValueError."""
        with pytest.raises(ValueError, match="text must not be empty"):
            run(text="   ", output_path="/tmp/out.mp3")
