"""TTS generation — text -> edge-tts -> ffmpeg normalize -> output."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import structlog

from middleware.quality_gate import ValidationResult
from middleware.quality_scorer import score_tts_generate
from scripts.audio.process_media import run as ffmpeg_run
from scripts.audio.speak_text import run as tts_run

logger = structlog.get_logger(__name__)


_KNOWN_VOICES = {
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-GB-SoniaNeural",
    "en-AU-NatashaNeural",
    "ms-MY-YasminNeural",
    "ms-MY-OsmanNeural",
}


def _validate_voice(voice: str | None) -> str:
    """Validate and default the TTS voice name.

    Args:
        voice: Edge TTS voice name, or None for default.

    Returns:
        Validated voice string.
    """
    if voice is None:
        return "en-US-AriaNeural"
    if voice not in _KNOWN_VOICES:
        logger.warning("Unknown voice '%s' — may fail at Edge TTS", voice)
    return voice


def _verify_output(file_path: str, text_length: int) -> ValidationResult:
    """L2 output verification for TTS audio files.

    Args:
        file_path: Path to the generated MP3 file.
        text_length: Length of the source text in characters.

    Returns:
        ValidationResult indicating pass/fail with error details.
    """
    errors: list[str] = []
    path = Path(file_path)

    if not path.exists():
        return ValidationResult(
            passed=False,
            errors=[f"Output file not found: {file_path}"],
            layer="output_verification",
        )

    size = path.stat().st_size
    if size == 0:
        return ValidationResult(
            passed=False,
            errors=["Output file is empty (0 bytes)"],
            layer="output_verification",
        )

    header = path.read_bytes()[:4]
    has_id3 = header[:3] == b"ID3"
    has_sync = len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
    if not has_id3 and not has_sync:
        errors.append("File does not have a valid MP3 header")

    min_expected = max(100, text_length * 50)
    if size < min_expected:
        errors.append(f"File suspiciously small ({size} bytes) for {text_length} chars")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        layer="output_verification",
    )


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
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH — required for audio normalization")
    try:
        import edge_tts  # noqa: F401  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("edge-tts package not installed — run: pip install edge-tts") from exc

    if not text.strip():
        msg = "text must not be empty"
        raise ValueError(msg)

    voice = _validate_voice(voice)

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

    # Step 3: L2 output verification
    quality_result = _verify_output(output_path, text_length=len(text))
    if not quality_result.passed:
        logger.warning(
            "TTS output quality check failed: %s", quality_result.errors
        )

    # Duration heuristic for longer text
    if quality_result.passed and len(text) > 50:
        min_duration_bytes = max(16_000, int((len(text) / 2.5) * 16_000))
        actual_size = Path(output_path).stat().st_size
        if actual_size < min_duration_bytes:
            logger.warning(
                "Audio duration suspect: %d bytes < %d minimum for %d chars",
                actual_size, min_duration_bytes, len(text),
            )

    score = score_tts_generate(Path(output_path), text_length=len(text))

    return {
        "file_path": output_path,
        "voice": voice,
        "status": "completed",
        "quality_report": {
            "passed": score.passed,
            "score": score.score,
            "properties": [
                {"name": p.name, "passed": p.passed, "detail": p.detail}
                for p in score.properties
            ],
            "layer": "output_verification",
        },
    }
