"""Derived human-readable views over the observational ledger."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from augments.observational.ledger import ReflectionRecord
from augments.observational.types import Observation


def compile_memory_markdown(
    *,
    observations: Sequence[Observation],
    reflections: Sequence[ReflectionRecord],
) -> str:
    """Render MEMORY.md as a derived artifact from structured memory."""

    active_observations = [observation for observation in observations if observation.status == "active"]
    active_reflections = [reflection for reflection in reflections if reflection.status == "active"]
    promoted_lessons = [reflection for reflection in active_reflections if reflection.promoted_lesson]

    lines = [
        "# Hermes Memory",
        "",
        "_Derived from structured observational memory; do not edit as source of truth._",
        "",
        "## Promoted Lessons",
    ]
    if promoted_lessons:
        for lesson in promoted_lessons:
            evidence = ", ".join(lesson.supporting_evidence[:2])
            lines.append(f"- {lesson.statement} (confidence: {lesson.confidence}; evidence: {evidence})")
    else:
        lines.append("- No promoted lessons yet.")

    lines.extend(["", "## Active Observations"])
    if active_observations:
        for observation in active_observations:
            evidence = ", ".join(observation.supporting_evidence[:2])
            lines.append(
                f"- [{observation.kind}] {observation.statement} "
                f"(confidence: {observation.confidence}; evidence: {evidence})"
            )
    else:
        lines.append("- No active observations yet.")

    lines.extend(["", "## Active Reflections"])
    if active_reflections:
        for reflection in active_reflections:
            evidence = ", ".join(reflection.supporting_evidence[:2])
            lines.append(
                f"- {reflection.statement} (confidence: {reflection.confidence}; evidence: {evidence})"
            )
    else:
        lines.append("- No active reflections yet.")

    return "\n".join(lines) + "\n"


def write_memory_markdown(
    *,
    memory_path: Path,
    observations: Sequence[Observation],
    reflections: Sequence[ReflectionRecord],
) -> str:
    """Write the derived MEMORY.md view and return the rendered content."""

    content = compile_memory_markdown(observations=observations, reflections=reflections)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(content, encoding="utf-8")
    return content


__all__ = [
    "compile_memory_markdown",
    "write_memory_markdown",
]
