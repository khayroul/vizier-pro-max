"""Edge TTS text-to-speech wrapper."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AriaNeural"


async def _async_generate(text: str, output_path: str, voice: str) -> str:
    """Async edge-tts generation.

    Args:
        text: Text to synthesize.
        output_path: Destination file path for the MP3.
        voice: Edge TTS voice name.

    Returns:
        Path to the generated audio file.
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    return output_path


def _generate_speech(*, text: str, output_path: str, voice: str) -> str:
    """Sync wrapper around async edge-tts.

    Args:
        text: Text to synthesize.
        output_path: Destination file path for the MP3.
        voice: Edge TTS voice name.

    Returns:
        Path to the generated audio file.
    """
    return asyncio.run(_async_generate(text, output_path, voice))


def run(
    *,
    text: str,
    output_path: str,
    voice: str | None = None,
) -> dict[str, str]:
    """Generate speech from text via Edge TTS.

    Args:
        text: Text to convert to speech. Must not be empty.
        output_path: Path for output MP3 file.
        voice: Voice name. Defaults to en-US-AriaNeural.

    Returns:
        Dict with file_path key pointing to the generated audio.

    Raises:
        ValueError: If text is empty or whitespace-only.
    """
    if not text.strip():
        msg = "text must not be empty"
        raise ValueError(msg)

    effective_voice = voice or DEFAULT_VOICE
    result_path = _generate_speech(
        text=text,
        output_path=output_path,
        voice=effective_voice,
    )
    logger.info("TTS saved to %s (voice: %s)", result_path, effective_voice)
    return {"file_path": result_path}
