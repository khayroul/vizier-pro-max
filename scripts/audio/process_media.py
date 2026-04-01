"""ffmpeg CLI wrapper for audio/video processing."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_PROJECT_OUTPUT = Path(__file__).resolve().parent.parent.parent / "output"


def _is_path_allowed(resolved_path: Path) -> bool:
    """Check if a path is within allowed output directories.

    Allows the project output/ dir by default, plus any dirs listed in
    VIZIER_ALLOWED_ROOTS (colon-separated), used by tests with tmp dirs.
    """
    if resolved_path.is_relative_to(_PROJECT_OUTPUT.resolve()):
        return True
    extra = os.environ.get("VIZIER_ALLOWED_ROOTS", "")
    if extra:
        for root in extra.split(":"):
            if root and resolved_path.is_relative_to(Path(root).resolve()):
                return True
    return False

_OPERATIONS = {"convert", "trim", "concat", "normalize", "extract_audio"}

_TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}:\d{2}(\.\d+)?$")


def _validate_time(time_str: str | None, param_name: str) -> None:
    """Validate a time string matches HH:MM:SS[.fraction] format.

    Args:
        time_str: Time string to validate, or None (no-op).
        param_name: Name of the parameter for error messages.

    Raises:
        ValueError: If the time string does not match the expected format.
    """
    if time_str is None:
        return
    if not _TIME_PATTERN.match(time_str):
        msg = (
            f"Invalid {param_name}: {time_str!r}. "
            "Expected format: HH:MM:SS or HH:MM:SS.fraction"
        )
        raise ValueError(msg)


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

    # Validate time parameters to prevent option injection
    _validate_time(start_time, "start_time")
    _validate_time(end_time, "end_time")

    # Validate output_path is within allowed directories
    resolved_output = Path(output_path).resolve()
    if not _is_path_allowed(resolved_output):
        msg = f"Output path escapes allowed directory: {output_path}"
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
    elif operation == "concat":
        all_paths = [input_path] + (concat_paths or [])
        list_content = "\n".join(f"file '{p}'" for p in all_paths)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(list_content)
            list_path = tmp.name
        try:
            cmd += [
                "-f", "concat", "-safe", "0",
                "-i", list_path, "-c", "copy", output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        finally:
            Path(list_path).unlink(missing_ok=True)
        logger.info("ffmpeg %s complete: %s", operation, output_path)
        return {"file_path": output_path}
    elif operation == "normalize":
        cmd += ["-i", input_path, "-af", "loudnorm", output_path]
    elif operation == "extract_audio":
        cmd += ["-i", input_path, "-vn", "-acodec", "libmp3lame", output_path]

    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    logger.info("ffmpeg %s complete: %s", operation, output_path)
    return {"file_path": output_path}
