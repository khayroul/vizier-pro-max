"""MEMORY.md size management -- keep under MAX_LINES."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_MEMORY_LINES = 200


def prune_memory(
    memory_dir: Path,
    max_lines: int = MAX_MEMORY_LINES,
) -> int:
    """Trim MEMORY.md to max_lines. Returns number of lines removed."""
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        return 0

    lines = memory_file.read_text().splitlines()
    if len(lines) <= max_lines:
        return 0

    # Keep most recent entries (bottom of file)
    removed = len(lines) - max_lines
    archive_file = memory_dir / "archive.md"

    # Append removed lines to archive
    archived_lines = lines[:removed]
    if archived_lines:
        existing_archive = archive_file.read_text() if archive_file.exists() else ""
        archive_file.write_text(existing_archive + "\n".join(archived_lines) + "\n")

    # Keep remaining lines
    memory_file.write_text("\n".join(lines[removed:]) + "\n")

    logger.info("Pruned %d lines from MEMORY.md", removed)
    return removed
