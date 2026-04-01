"""Bridge entry point — runs all bridge components.

Trigger: post-commit git hook + launchd cron (5-min fallback).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import structlog  # type: ignore[import-untyped]

from bridge import manifest_syncer

logger = structlog.get_logger(__name__)

_STATE_FILE = Path.home() / ".vizier-pro-max" / "bridge-state.json"


def _load_state() -> dict[str, dict[str, float]]:
    """Load bridge state from disk."""
    if not _STATE_FILE.exists():
        return {"manifests": {}, "pipelines": {}}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupt state file, starting fresh: %s", exc)
        return {"manifests": {}, "pipelines": {}}


def _save_state(state: dict[str, dict[str, float]]) -> None:
    """Persist bridge state to disk (atomic via temp + rename)."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_STATE_FILE.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp_path, str(_STATE_FILE))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def run(repo_path: Path | None = None) -> None:
    """Run all bridge components.

    Args:
        repo_path: Path to the vizier-pro-max repo root.
    """
    if repo_path is None:
        repo_path = Path(__file__).parent.parent

    state = _load_state()

    # 1. Git watcher: commits -> MEMORY.md
    try:
        from bridge import git_watcher
        git_watcher.run(repo_path)
    except (
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        logger.warning("Git watcher failed: %s", exc, exc_info=True)

    # 2. Skill syncer: repo <-> ~/.hermes/skills/vizier/
    try:
        from bridge import skill_syncer
        repo_skills = repo_path / "skills"
        hermes_skills = Path.home() / ".hermes" / "skills" / "vizier"
        if repo_skills.is_dir():
            skill_syncer.sync_repo_to_hermes(repo_skills, hermes_skills)
            skill_syncer.sync_hermes_to_repo(hermes_skills, repo_skills)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Skill syncer failed: %s", exc, exc_info=True)

    # 3. Manifest syncer: detect new tools/pipelines
    manifests_dir = repo_path / "manifests"
    pipelines_dir = repo_path / "pipelines"

    manifest_state = state.get("manifests", {})
    pipeline_state = state.get("pipelines", {})

    new_manifests, manifest_state = manifest_syncer.check_new_manifests(
        manifests_dir, manifest_state
    )
    new_pipelines, pipeline_state = manifest_syncer.check_new_pipelines(
        pipelines_dir, pipeline_state
    )

    if new_manifests:
        logger.info("New manifests detected: %s", new_manifests)
    if new_pipelines:
        logger.info("New pipelines detected: %s", new_pipelines)

    updated_state = {**state, "manifests": manifest_state, "pipelines": pipeline_state}
    _save_state(updated_state)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    run()
