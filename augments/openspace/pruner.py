"""Archive stale skills that haven't been used in N sessions."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from augments.openspace.version_dag import VersionDAG

logger = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD = 10  # sessions without invocation


def prune_stale_skills(
    dag: VersionDAG,
    skills_dir: Path,
    archive_dir: Path | None = None,
    threshold: int = DEFAULT_STALE_THRESHOLD,
) -> list[str]:
    """Move stale skills to archive. Returns list of pruned skill IDs.

    A skill is pruned when it is a derivative (generation > 0) with zero
    total usage (selections + completions).  Root/imported skills with no
    usage are kept because they haven't had a chance yet.
    """
    archive = archive_dir or skills_dir / "_archived"
    archive.mkdir(parents=True, exist_ok=True)

    pruned: list[str] = []
    for record in dag.list_active():
        total_use = record.total_selections + record.total_completions
        if total_use == 0 and record.generation == 0:
            continue  # Skip imported root skills -- they haven't had a chance yet
        if total_use > 0:
            continue  # Still in use -- keep active
        # Derivative with zero use -- archive it
        if record.path.exists():
            dest = archive / f"{record.skill_id}_{record.path.name}"
            shutil.move(str(record.path), str(dest))
            logger.info("Archived stale skill: %s -> %s", record.path, dest)
        dag.deactivate(record.skill_id)
        pruned.append(record.skill_id)

    return pruned
