"""Merge delegate_task child results into a unified deliverable.

Uses order-preserving deduplication for file paths (DeerFlow pattern).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FILE_PATH_PATTERN = re.compile(r"(?:output|tmp)/[\w/\-\.]+\.\w+")


def _extract_file_paths(text: str) -> list[str]:
    """Extract file paths from result text."""
    return _FILE_PATH_PATTERN.findall(text)


def _dedup_preserve_order(items: list[str]) -> list[str]:
    """Deduplicate while preserving order (DeerFlow dict.fromkeys pattern)."""
    return list(dict.fromkeys(items))


def merge(
    *,
    results: list[str],
    output_format: str = "summary",
) -> dict[str, Any]:
    """Merge child task results into a unified deliverable.

    Args:
        results: List of result strings from child tasks.
        output_format: Desired output format label (e.g. "summary", "report").

    Returns:
        Dict with keys: merged (str), artifacts (list[str]),
        format (str), result_count (int).
    """
    if not results:
        return {"merged": "", "artifacts": [], "format": output_format}

    # Collect all file paths, deduplicate
    all_paths: list[str] = []
    for result in results:
        all_paths.extend(_extract_file_paths(result))
    artifacts = _dedup_preserve_order(all_paths)

    # Merge text with section separators
    sections = []
    for i, result in enumerate(results, 1):
        sections.append(f"--- Result {i} ---\n{result}")
    merged = "\n\n".join(sections)

    logger.info(
        "Merged %d results, %d unique artifacts", len(results), len(artifacts)
    )
    return {
        "merged": merged,
        "artifacts": artifacts,
        "format": output_format,
        "result_count": len(results),
    }
