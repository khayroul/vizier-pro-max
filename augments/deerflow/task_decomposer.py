"""Decompose complex tasks into parallel sub-task specs for delegate_task batch mode.

Output format is compatible with Hermes delegate_task(tasks=[...]).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_CHILDREN = 3

_TOOLSET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)research|analyze|data|market|trend|survey|competitor"),
        "vizier-research",
    ),
    (
        re.compile(r"(?i)poster|image|design|visual|screenshot|photo|graphic"),
        "vizier-visual",
    ),
    (
        re.compile(r"(?i)copy|content|write|social|caption|blog|article|email"),
        "vizier-content",
    ),
    (
        re.compile(r"(?i)pdf|report|invoice|document|convert|merge"),
        "vizier-document",
    ),
    (
        re.compile(r"(?i)audio|voice|tts|podcast|sound|music|speak"),
        "vizier-audio",
    ),
]


def _classify_segment(text: str) -> str:
    """Match a text segment to a toolset via keyword patterns."""
    for pattern, toolset in _TOOLSET_PATTERNS:
        if pattern.search(text):
            return toolset
    return "vizier-fallback"


def _split_into_segments(task_description: str) -> list[str]:
    """Split a compound task into segments by common delimiters."""
    segments = re.split(r",\s*(?:and\s+)?|;\s*|\band\b", task_description)
    return [s.strip() for s in segments if s.strip()]


def decompose(task_description: str) -> dict[str, Any]:
    """Decompose a task into sub-task specs for delegate_task batch mode.

    Args:
        task_description: Natural language description of the work to perform.

    Returns:
        {"tasks": [{goal, context, toolsets}, ...], "summary": "..."}
    """
    segments = _split_into_segments(task_description)

    # Group segments by toolset to avoid duplicate toolset assignments
    toolset_groups: dict[str, list[str]] = {}
    for segment in segments:
        toolset = _classify_segment(segment)
        toolset_groups.setdefault(toolset, []).append(segment)

    tasks: list[dict[str, Any]] = []
    for toolset, segs in toolset_groups.items():
        goal = "; ".join(segs)
        tasks.append({
            "goal": goal,
            "context": task_description,
            "toolsets": [toolset],
        })

    # Cap at MAX_CHILDREN
    if len(tasks) > MAX_CHILDREN:
        logger.warning(
            "Decomposed into %d tasks, capping at %d", len(tasks), MAX_CHILDREN
        )
        tasks = tasks[:MAX_CHILDREN]

    # Fallback: if no segments matched, single task with fallback
    if not tasks:
        tasks = [{
            "goal": task_description,
            "context": task_description,
            "toolsets": ["vizier-fallback"],
        }]

    summary = f"Decomposed into {len(tasks)} parallel sub-tasks"
    logger.info(summary)
    return {"tasks": tasks, "summary": summary}
