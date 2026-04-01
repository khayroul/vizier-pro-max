"""Dual-strategy test discovery and confidence mapping.

Finds test files for source modules using two strategies:
1. Vizier convention: vizier/X.py -> tests/vizier/test_X.py
2. Reactor co-located: reactor/a/b.py -> reactor/a/tests/test_b.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog  # type: ignore[import-untyped]

logger = structlog.get_logger(__name__)

_TEST_FUNC_RE = re.compile(r"^def (test_\w+)", re.MULTILINE)


@dataclass(frozen=True)
class ModuleConfidence:
    """Test coverage confidence for a single source module.

    Attributes:
        source_path: Relative path to the source file.
        test_path: Absolute path to the discovered test file, or None.
        test_count: Number of ``def test_*`` functions found.
        confidence: Classification based on test_count.
    """

    source_path: str
    test_path: str | None
    test_count: int
    confidence: Literal["high", "medium", "low", "none"]


def find_test_file(source_path: str, repo_root: Path) -> Path | None:
    """Locate the test file for a source module using dual-strategy lookup.

    Args:
        source_path: Relative path from repo root (e.g. ``vizier/tools/engines.py``).
        repo_root: Absolute path to the repository root.

    Returns:
        Absolute ``Path`` to the test file, or ``None`` if no strategy matches.
    """
    parts = Path(source_path)
    stem = parts.stem

    # Strategy 1 (vizier convention): vizier/tools/X.py -> tests/vizier/tools/test_X.py
    strategy_one = repo_root / "tests" / parts.parent / f"test_{stem}.py"
    if strategy_one.is_file():
        return strategy_one

    # Strategy 2 (reactor co-located):
    # reactor/engine/e3_text/e3.py -> reactor/engine/e3_text/tests/test_e3.py
    strategy_two = repo_root / parts.parent / "tests" / f"test_{stem}.py"
    if strategy_two.is_file():
        return strategy_two

    return None


def _count_tests(test_file: Path) -> int:
    """Count ``def test_*`` function definitions in a test file.

    Args:
        test_file: Absolute path to a Python test file.

    Returns:
        Number of test functions found.
    """
    try:
        content = test_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Cannot read test file %s: %s", test_file, exc)
        return 0
    return len(_TEST_FUNC_RE.findall(content))


def _classify_confidence(
    test_count: int,
    test_file_exists: bool,
) -> Literal["high", "medium", "low", "none"]:
    """Map test count and file existence to a confidence level.

    Args:
        test_count: Number of test functions discovered.
        test_file_exists: Whether a test file was found on disk.

    Returns:
        Confidence literal: high (5+), medium (1-4), low (file but 0), none (no file).
    """
    if not test_file_exists:
        return "none"
    if test_count >= 5:
        return "high"
    if test_count >= 1:
        return "medium"
    return "low"


def parse_module_confidence(
    source_path: str,
    repo_root: Path,
) -> ModuleConfidence:
    """Build a ``ModuleConfidence`` for the given source module.

    Args:
        source_path: Relative path from repo root.
        repo_root: Absolute path to the repository root.

    Returns:
        Frozen ``ModuleConfidence`` dataclass with discovery results.
    """
    test_file = find_test_file(source_path, repo_root)
    test_file_exists = test_file is not None
    test_count = _count_tests(test_file) if test_file is not None else 0
    confidence = _classify_confidence(test_count, test_file_exists)

    return ModuleConfidence(
        source_path=source_path,
        test_path=str(test_file) if test_file is not None else None,
        test_count=test_count,
        confidence=confidence,
    )
