"""TTS generation — text → edge-tts → ffmpeg normalize → output.

Gate 2 stub.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run(
    *,
    text: str,
    output_path: str = "output/audio/speech.mp3",
    voice: str | None = None,
) -> dict[str, str]:
    """Generate TTS audio from text."""
    logger.info("tts_generate stub: text=%s...", text[:50])
    return {
        "status": "stub",
        "message": "tts_generate pipeline not yet implemented",
        "output_path": output_path,
    }
