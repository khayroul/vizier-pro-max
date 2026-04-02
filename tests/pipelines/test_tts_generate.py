"""Tests for tts_generate pipeline."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipelines.tts_generate import run


def _make_fake_mp3(path: Path, size: int = 50_000) -> None:
    """Write a minimal fake MP3 file with an ID3 header."""
    data = b"ID3" + b"\x00" * (size - 3)
    path.write_bytes(data)


class TestTtsGenerate:
    def test_generates_normalized_audio(self, tmp_path: Path) -> None:
        """Full pipeline: TTS -> normalize -> output."""
        output = str(tmp_path / "speech.mp3")
        _make_fake_mp3(tmp_path / "speech.mp3")

        fake_score = MagicMock()
        fake_score.passed = True
        fake_score.score = 8.5
        fake_score.properties = []

        with patch("pipelines.tts_generate.tts_run") as mock_tts, \
             patch("pipelines.tts_generate.ffmpeg_run") as mock_ffmpeg, \
             patch("pipelines.tts_generate.score_tts_generate", return_value=fake_score), \
             patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch.dict(sys.modules, {"edge_tts": MagicMock()}):
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
        _make_fake_mp3(tmp_path / "speech.mp3")

        fake_score = MagicMock()
        fake_score.passed = True
        fake_score.score = 8.0
        fake_score.properties = []

        with patch("pipelines.tts_generate.tts_run") as mock_tts, \
             patch("pipelines.tts_generate.ffmpeg_run") as mock_ffmpeg, \
             patch("pipelines.tts_generate.score_tts_generate", return_value=fake_score), \
             patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch.dict(sys.modules, {"edge_tts": MagicMock()}):
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
        """Empty text raises ValueError after dependency checks pass."""
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch.dict(sys.modules, {"edge_tts": MagicMock()}):
            with pytest.raises(ValueError, match="text must not be empty"):
                run(text="   ", output_path="/tmp/out.mp3")

    def test_raises_without_ffmpeg(self) -> None:
        """RuntimeError raised when ffmpeg is missing from PATH."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                run(text="hello", output_path="/tmp/test.mp3")

    def test_raises_without_edge_tts(self) -> None:
        """RuntimeError raised when edge-tts package is not installed."""
        import builtins
        real_import = builtins.__import__

        def _import_raiser(name: str, *args: object, **kwargs: object) -> object:
            if name == "edge_tts":
                raise ImportError("No module named 'edge_tts'")
            return real_import(name, *args, **kwargs)

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch("builtins.__import__", side_effect=_import_raiser):
            with pytest.raises(RuntimeError, match="edge-tts package not installed"):
                run(text="hello", output_path="/tmp/test.mp3")

    def test_quality_report_uses_scorer(self, tmp_path: Path) -> None:
        """quality_report in return dict uses score_tts_generate output."""
        output = str(tmp_path / "speech.mp3")
        _make_fake_mp3(tmp_path / "speech.mp3")

        fake_prop = MagicMock()
        fake_prop.name = "mp3_header_valid"
        fake_prop.passed = True
        fake_prop.detail = "ID3 header found"

        fake_score = MagicMock()
        fake_score.passed = True
        fake_score.score = 9.0
        fake_score.properties = [fake_prop]

        with patch("pipelines.tts_generate.tts_run") as mock_tts, \
             patch("pipelines.tts_generate.ffmpeg_run") as mock_ffmpeg, \
             patch("pipelines.tts_generate.score_tts_generate", return_value=fake_score) as mock_scorer, \
             patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch.dict(sys.modules, {"edge_tts": MagicMock()}):
            mock_tts.return_value = {"file_path": str(tmp_path / "raw.mp3")}
            mock_ffmpeg.return_value = {"file_path": output}

            result = run(text="Hello world", output_path=output)

        mock_scorer.assert_called_once_with(Path(output), text_length=len("Hello world"))
        qr = result["quality_report"]
        assert qr["passed"] is True
        assert qr["score"] == 9.0
        assert qr["layer"] == "output_verification"
        assert len(qr["properties"]) == 1
        assert qr["properties"][0]["name"] == "mp3_header_valid"
