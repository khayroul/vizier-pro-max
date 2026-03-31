"""Bi-directional skill sync between repo and Hermes runtime."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"


def sync_repo_to_hermes(
    repo_vizier_skills: Path,
    hermes_vizier_skills: Path,
) -> int:
    """Copy repo skills to Hermes runtime directory.

    Newer mtime wins on conflict: if Hermes copy is newer, it is preserved.

    Args:
        repo_vizier_skills: Path to repo-side skill directories.
        hermes_vizier_skills: Path to Hermes-side skill directories.

    Returns:
        Number of skills synced (copied or updated).
    """
    if not repo_vizier_skills.is_dir():
        return 0

    synced = 0
    for skill_dir in sorted(repo_vizier_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        repo_file = skill_dir / SKILL_FILENAME
        if not repo_file.is_file():
            continue

        target_dir = hermes_vizier_skills / skill_dir.name
        target_file = target_dir / SKILL_FILENAME

        hermes_mtime = target_file.stat().st_mtime if target_file.is_file() else -1.0
        if target_file.is_file() and hermes_mtime >= repo_file.stat().st_mtime:
            logger.debug("Skipping %s: Hermes copy is newer", skill_dir.name)
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_file, target_file)
        logger.info("Synced repo -> hermes: %s", skill_dir.name)
        synced += 1

    return synced


def sync_hermes_to_repo(
    hermes_vizier_skills: Path,
    repo_vizier_skills: Path,
) -> int:
    """Copy Hermes-created skills that are absent from repo.

    Only new skills are copied; existing repo skills are never overwritten.

    Args:
        hermes_vizier_skills: Path to Hermes-side skill directories.
        repo_vizier_skills: Path to repo-side skill directories.

    Returns:
        Number of new skills synced to repo.
    """
    if not hermes_vizier_skills.is_dir():
        return 0

    synced = 0
    for skill_dir in sorted(hermes_vizier_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        hermes_file = skill_dir / SKILL_FILENAME
        if not hermes_file.is_file():
            continue

        target_dir = repo_vizier_skills / skill_dir.name
        target_file = target_dir / SKILL_FILENAME

        if target_file.exists():
            logger.debug("Skipping %s: already in repo", skill_dir.name)
            continue

        repo_vizier_skills.mkdir(parents=True, exist_ok=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hermes_file, target_file)
        logger.info("Synced hermes -> repo: %s", skill_dir.name)
        synced += 1

    return synced
