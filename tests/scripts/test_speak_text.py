"""Tests for edge_tts_speak wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSpeakText:
    def test_speak_produces_audio(self, tmp_path: Path) -> None:
        from scripts.audio.speak_text import run

        output = tmp_path / "speech.mp3"
        with patch("scripts.audio.speak_text._generate_speech") as mock_gen:
            mock_gen.return_value = str(output)
            output.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)  # fake MP3
            result = run(
                text="Hello world",
                output_path=str(output),
            )
        assert result["file_path"] == str(output)

    def test_speak_custom_voice(self, tmp_path: Path) -> None:
        from scripts.audio.speak_text import run

        output = tmp_path / "speech.mp3"
        with patch("scripts.audio.speak_text._generate_speech") as mock_gen:
            mock_gen.return_value = str(output)
            output.write_bytes(b"\x00" * 100)
            run(
                text="Selamat pagi",
                output_path=str(output),
                voice="ms-MY-YasminNeural",
            )
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["voice"] == "ms-MY-YasminNeural"

    def test_speak_empty_text_raises(self) -> None:
        from scripts.audio.speak_text import run

        with pytest.raises(ValueError, match="text must not be empty"):
            run(text="", output_path="/tmp/out.mp3")
