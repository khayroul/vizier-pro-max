"""Pandoc CLI wrapper for document format conversion."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_FORMAT_MAP = {
    ".md": "markdown",
    ".html": "html",
    ".docx": "docx",
    ".pdf": "pdf",
    ".tex": "latex",
    ".rst": "rst",
    ".txt": "plain",
}


def run(
    *,
    input_path: str,
    output_path: str,
    from_format: str | None = None,
    to_format: str | None = None,
) -> dict[str, str]:
    """Convert between document formats via pandoc.

    Args:
        input_path: Path to input file.
        output_path: Path for output file.
        from_format: Input format (auto-detected from extension if omitted).
        to_format: Output format (auto-detected from extension if omitted).

    Returns:
        Dict with ``file_path`` key pointing to the converted file.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)

    _VALID_FORMATS = set(_FORMAT_MAP.values())

    if from_format is not None and from_format not in _VALID_FORMATS:
        msg = (
            f"Disallowed from_format: {from_format!r}."
            f" Valid: {sorted(_VALID_FORMATS)}"
        )
        raise ValueError(msg)
    if to_format is not None and to_format not in _VALID_FORMATS:
        msg = f"Disallowed to_format: {to_format!r}. Valid: {sorted(_VALID_FORMATS)}"
        raise ValueError(msg)

    effective_from = from_format or _FORMAT_MAP.get(in_path.suffix, "markdown")
    effective_to = to_format or _FORMAT_MAP.get(out_path.suffix, "html")

    if not shutil.which("pandoc"):
        msg = "pandoc binary not found on PATH"
        raise FileNotFoundError(msg)

    cmd = [
        "pandoc",
        "-f", effective_from,
        "-t", effective_to,
        "-o", str(out_path),
        str(in_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    logger.info("Converted %s → %s", in_path.name, out_path.name)
    return {"file_path": str(out_path)}
