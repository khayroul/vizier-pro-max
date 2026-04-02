"""Bridge entry point — runs all bridge components.

Trigger: post-commit git hook + launchd cron (5-min fallback).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import structlog  # type: ignore[import-untyped]

from bridge import manifest_syncer
from bridge.build_capture import capture_external_build_event
from bridge.session_capture import sync_prompt_log_to_build_capture

logger = structlog.get_logger(__name__)

_STATE_FILE = Path.home() / ".vizier-pro-max" / "bridge-state.json"


def _default_state() -> dict[str, dict[str, float]]:
    return {
        "manifests": {},
        "pipelines": {},
        "runtime_capture": {"last_prompt_log_id": 0.0},
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_state(state: object) -> dict[str, dict[str, float]]:
    normalized = _default_state()
    if not isinstance(state, dict):
        return normalized

    for section in normalized:
        value = state.get(section, {})
        if not isinstance(value, dict):
            continue
        cleaned = dict(normalized[section])
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, (int, float)):
                continue
            cleaned[key] = float(item)
        normalized[section] = cleaned
    return normalized


def _changed_paths(
    previous: dict[str, float],
    current: dict[str, float],
    repo_path: Path,
) -> tuple[str, ...]:
    repo_root = repo_path.resolve()
    changed: list[str] = []
    for path_str, mtime in current.items():
        if previous.get(path_str) == mtime:
            continue
        path = Path(path_str)
        try:
            changed.append(path.resolve().relative_to(repo_root).as_posix())
        except ValueError:
            changed.append(path.as_posix())
    return tuple(sorted(changed))


def _capture_sync_event(
    *,
    repo_path: Path,
    task_id: str,
    event_type: str,
    summary: str,
    files_touched: tuple[str, ...],
    artifacts: tuple[str, ...],
    metadata: dict[str, object],
    labels: tuple[str, ...],
) -> None:
    if not files_touched and not artifacts:
        return
    capture_external_build_event(
        source="vizier",
        task_id=task_id,
        event_type=event_type,
        summary=summary,
        status="ok",
        timestamp=_now_iso(),
        state_root=repo_path / "state",
        files_touched=files_touched,
        artifacts=artifacts,
        labels=labels,
        trace_refs=("bridge_state:watcher",),
        metadata=metadata,
    )


def _load_state() -> dict[str, dict[str, float]]:
    """Load bridge state from disk."""
    if not _STATE_FILE.exists():
        return _default_state()
    try:
        return _normalize_state(json.loads(_STATE_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupt state file, starting fresh: %s", exc)
        return _default_state()


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

    # 3. Runtime capture: prompt_log -> build capture ledger
    runtime_capture_state = state.get("runtime_capture", {})
    last_prompt_log_id = int(runtime_capture_state.get("last_prompt_log_id", 0.0))
    try:
        session_sync_result = sync_prompt_log_to_build_capture(
            state_root=repo_path / "state",
            after_row_id=last_prompt_log_id,
        )
        runtime_capture_state = {
            "last_prompt_log_id": float(session_sync_result.last_prompt_log_id),
        }
    except (sqlite3.Error, OSError, ValueError) as exc:
        logger.warning("Session capture failed: %s", exc, exc_info=True)

    # 4. Manifest syncer: detect new tools/pipelines
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
        manifest_paths = _changed_paths(state.get("manifests", {}), manifest_state, repo_path)
        manifest_mtimes = {
            path: manifest_state[str(repo_path / path)] if str(repo_path / path) in manifest_state else 0.0
            for path in manifest_paths
        }
        _capture_sync_event(
            repo_path=repo_path,
            task_id="bridge-watcher.manifests",
            event_type="artifact_created",
            summary=f"Detected {len(new_manifests)} new or updated manifests",
            files_touched=manifest_paths,
            artifacts=tuple(new_manifests),
            labels=("watcher", "manifest_syncer"),
            metadata={"watcher": "manifest_syncer", "mtimes": manifest_mtimes},
        )
    if new_pipelines:
        logger.info("New pipelines detected: %s", new_pipelines)
        pipeline_paths = _changed_paths(state.get("pipelines", {}), pipeline_state, repo_path)
        pipeline_mtimes = {
            path: pipeline_state[str(repo_path / path)] if str(repo_path / path) in pipeline_state else 0.0
            for path in pipeline_paths
        }
        _capture_sync_event(
            repo_path=repo_path,
            task_id="bridge-watcher.pipelines",
            event_type="file_changed",
            summary=f"Detected {len(new_pipelines)} new or updated pipelines",
            files_touched=pipeline_paths,
            artifacts=tuple(new_pipelines),
            labels=("watcher", "pipeline_syncer"),
            metadata={"watcher": "pipeline_syncer", "mtimes": pipeline_mtimes},
        )

    updated_state = {
        **state,
        "runtime_capture": runtime_capture_state,
        "manifests": manifest_state,
        "pipelines": pipeline_state,
    }
    _save_state(updated_state)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    run()
