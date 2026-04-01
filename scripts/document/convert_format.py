"""Pandoc CLI wrapper for document format conversion."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

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

    effective_from = from_format or _FORMAT_MAP.get(in_path.suffix, "markdown")
    effective_to = to_format or _FORMAT_MAP.get(out_path.suffix, "html")

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
