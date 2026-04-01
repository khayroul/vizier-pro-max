"""ffmpeg CLI wrapper for audio/video processing."""
from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

_OPERATIONS = {"convert", "trim", "concat", "normalize", "extract_audio"}


def run(
    *,
    input_path: str,
    output_path: str,
    operation: str,
    start_time: str | None = None,
    end_time: str | None = None,
    concat_paths: list[str] | None = None,
) -> dict[str, str]:
    """Process audio/video via ffmpeg.

    Args:
        input_path: Path to input audio/video file.
        output_path: Path for output file.
        operation: Operation to perform — convert, trim, concat, normalize,
            extract_audio.
        start_time: Start time for trim (HH:MM:SS).
        end_time: End time for trim (HH:MM:SS).
        concat_paths: Additional files to concatenate.

    Returns:
        Dict with file_path key pointing to the processed file.

    Raises:
        ValueError: If operation is not recognized.
    """
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    cmd: list[str] = ["ffmpeg", "-y"]

    if operation == "convert":
        cmd += ["-i", input_path, output_path]
    elif operation == "trim":
        cmd += ["-i", input_path]
        if start_time:
            cmd += ["-ss", start_time]
        if end_time:
            cmd += ["-to", end_time]
        cmd += ["-c", "copy", output_path]
    elif operation == "normalize":
        cmd += ["-i", input_path, "-af", "loudnorm", output_path]
    elif operation == "extract_audio":
        cmd += ["-i", input_path, "-vn", "-acodec", "libmp3lame", output_path]

    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    logger.info("ffmpeg %s complete: %s", operation, output_path)
    return {"file_path": output_path}
