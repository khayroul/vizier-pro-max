"""Bridge entry point — runs all bridge components.

Trigger: post-commit git hook + launchd cron (5-min fallback).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from bridge import manifest_syncer

logger = logging.getLogger(__name__)

_STATE_FILE = Path.home() / ".vizier-pro-max" / "bridge-state.json"


def _load_state() -> dict[str, dict[str, float]]:
    """Load bridge state from disk."""
    if not _STATE_FILE.exists():
        return {"manifests": {}, "pipelines": {}}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"manifests": {}, "pipelines": {}}


def _save_state(state: dict[str, dict[str, float]]) -> None:
    """Persist bridge state to disk."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


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
    except Exception as exc:
        logger.warning("Git watcher failed: %s", exc)

    # 2. Skill syncer: repo <-> ~/.hermes/skills/vizier/
    try:
        from bridge import skill_syncer
        repo_skills = repo_path / "skills"
        hermes_skills = Path.home() / ".hermes" / "skills" / "vizier"
        if repo_skills.is_dir():
            skill_syncer.sync_repo_to_hermes(repo_skills, hermes_skills)
            skill_syncer.sync_hermes_to_repo(hermes_skills, repo_skills)
    except Exception as exc:
        logger.warning("Skill syncer failed: %s", exc)

    # 3. Manifest syncer: detect new tools/pipelines
    manifests_dir = repo_path / "manifests"
    pipelines_dir = repo_path / "pipelines"

    manifest_state = state.get("manifests", {})
    pipeline_state = state.get("pipelines", {})

    new_manifests = manifest_syncer.check_new_manifests(manifests_dir, manifest_state)
    new_pipelines = manifest_syncer.check_new_pipelines(pipelines_dir, pipeline_state)

    if new_manifests:
        logger.info("New manifests detected: %s", new_manifests)
    if new_pipelines:
        logger.info("New pipelines detected: %s", new_pipelines)

    state["manifests"] = manifest_state
    state["pipelines"] = pipeline_state
    _save_state(state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
