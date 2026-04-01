"""TTS generation — text -> edge-tts -> ffmpeg normalize -> output."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import structlog

from scripts.audio.process_media import run as ffmpeg_run
from scripts.audio.speak_text import run as tts_run

logger = structlog.get_logger(__name__)


def run(
    *,
    text: str,
    output_path: str = "output/audio/speech.mp3",
    voice: str | None = None,
) -> dict[str, Any]:
    """Generate TTS audio from text, normalized via ffmpeg.

    Args:
        text: Text to synthesize. Must not be empty.
        output_path: Final output MP3 path.
        voice: Edge TTS voice name (default: en-US-AriaNeural).

    Returns:
        Dict with file_path, voice, and status keys.
    """
    if not text.strip():
        msg = "text must not be empty"
        raise ValueError(msg)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate raw TTS audio
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        raw_path = tmp.name

    try:
        tts_result = tts_run(text=text, output_path=raw_path, voice=voice)
        raw_file = tts_result["file_path"]
        logger.info("TTS raw audio generated: %s", raw_file)

        # Step 2: Normalize audio via ffmpeg
        ffmpeg_result = ffmpeg_run(
            input_path=raw_file,
            output_path=output_path,
            operation="normalize",
        )
        logger.info("TTS normalized audio: %s", ffmpeg_result["file_path"])
    finally:
        Path(raw_path).unlink(missing_ok=True)

    return {
        "file_path": output_path,
        "voice": voice or "en-US-AriaNeural",
        "status": "completed",
    }
