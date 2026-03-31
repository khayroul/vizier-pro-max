"""Manifest syncer — detect new/updated manifests and pipelines.

Watches manifests/ and pipelines/ directories. Updates are available
on next Hermes session start (not mid-session).
"""
from __future__ import annotations

import logging
from pathlib import Path

from adapter.schemas import parse_manifest

logger = logging.getLogger(__name__)


def check_new_manifests(
    manifests_dir: Path,
    state: dict[str, float],
) -> list[str]:
    """Check for new or modified manifest YAML files.

    Args:
        manifests_dir: Root manifests directory.
        state: Dict mapping file paths to last-seen mtime.

    Returns:
        List of new/updated manifest names.
    """
    new_names: list[str] = []

    if not manifests_dir.is_dir():
        return new_names

    for yaml_path in sorted(manifests_dir.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue

        path_str = str(yaml_path)
        current_mtime = yaml_path.stat().st_mtime
        last_mtime = state.get(path_str, 0.0)

        if current_mtime > last_mtime:
            try:
                content = yaml_path.read_text(encoding="utf-8")
                config = parse_manifest(content)
                new_names.append(config.name)
                state[path_str] = current_mtime
                logger.info("New/updated manifest: %s", config.name)
            except (ValueError, OSError) as exc:
                logger.warning("Skipping invalid manifest %s: %s", yaml_path, exc)

    return new_names


def check_new_pipelines(
    pipelines_dir: Path,
    state: dict[str, float],
) -> list[str]:
    """Check for new or modified pipeline scripts.

    Args:
        pipelines_dir: Pipelines directory.
        state: Dict mapping file paths to last-seen mtime.

    Returns:
        List of new/updated pipeline names.
    """
    new_names: list[str] = []

    if not pipelines_dir.is_dir():
        return new_names

    for py_path in sorted(pipelines_dir.glob("*.py")):
        if py_path.name.startswith("_"):
            continue

        path_str = str(py_path)
        current_mtime = py_path.stat().st_mtime
        last_mtime = state.get(path_str, 0.0)

        if current_mtime > last_mtime:
            new_names.append(py_path.stem)
            state[path_str] = current_mtime
            logger.info("New/updated pipeline: %s", py_path.stem)

    return new_names
