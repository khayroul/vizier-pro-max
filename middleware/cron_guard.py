"""Safety layer for unattended cron sessions.

Checks tool test coverage, enforces token budget, holds delivery below threshold.
"""
from __future__ import annotations

from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent


def _tools_have_tests(toolsets: list[str]) -> bool:
    """Check that all tools in the given toolsets have test files.

    Uses test_parser to find test files for each script referenced by
    the toolset's manifests.
    """
    from adapter.schemas import parse_manifest
    from bridge.test_parser import find_test_file

    manifests_dir = _PROJECT_ROOT / "manifests"
    for toolset in toolsets:
        for yaml_file in manifests_dir.rglob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            try:
                manifest = parse_manifest(yaml_file.read_text())
            except (yaml.YAMLError, OSError, ValueError, KeyError):
                continue
            if manifest.toolset != toolset:
                continue
            if manifest.execution and manifest.execution.entrypoint is not None:
                entrypoint = manifest.execution.entrypoint
                module_path = entrypoint.split(":")[0].replace(".", "/") + ".py"
                test_file = find_test_file(module_path, _PROJECT_ROOT)
                if test_file is None:
                    logger.warning(
                        "No test file for %s (toolset: %s)", module_path, toolset
                    )
                    return False
    return True


def check_job_safety(
    *,
    toolsets: list[str],
    token_budget: int,
) -> dict[str, bool | str]:
    """Check if a cron job is safe to execute."""
    if not _tools_have_tests(toolsets):
        return {
            "allowed": False,
            "reason": "Job uses untested tools — blocked for safety",
        }
    return {"allowed": True, "reason": "All tools tested"}


def enforce_token_budget(*, used: int, budget: int) -> bool:
    """Return True if within budget, False if exceeded."""
    if used > budget:
        logger.warning("Token budget exceeded: %d / %d", used, budget)
        return False
    return True


def should_hold_delivery(*, score: float, threshold: float = 7.0) -> bool:
    """Return True if delivery should be held for human review."""
    return score < threshold
