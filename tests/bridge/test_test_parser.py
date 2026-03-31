"""Tests for vizier.adapter.test_parser — dual-strategy test discovery."""
from __future__ import annotations

from pathlib import Path

import pytest

from bridge.test_parser import (
    ModuleConfidence,
    find_test_file,
    parse_module_confidence,
)


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for test discovery."""
    return tmp_path


class TestFindTestFile:
    """Tests for find_test_file dual-strategy discovery."""

    def test_vizier_convention(self, tmp_repo: Path) -> None:
        """Strategy 1: vizier/tools/X.py -> tests/vizier/tools/test_X.py."""
        test_file = tmp_repo / "tests" / "vizier" / "tools" / "test_engines.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def test_example(): pass\n")

        result = find_test_file("vizier/tools/engines.py", tmp_repo)

        assert result is not None
        assert result == test_file

    def test_reactor_colocated(self, tmp_repo: Path) -> None:
        """Strategy 2: reactor/engine/e3_text/e3.py -> reactor/engine/e3_text/tests/test_e3.py."""
        test_file = (
            tmp_repo / "reactor" / "engine" / "e3_text" / "tests" / "test_e3.py"
        )
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def test_something(): pass\n")

        result = find_test_file("reactor/engine/e3_text/e3.py", tmp_repo)

        assert result is not None
        assert result == test_file

    def test_returns_none_when_missing(self, tmp_repo: Path) -> None:
        """Returns None when neither strategy finds a test file."""
        result = find_test_file("vizier/tools/nonexistent.py", tmp_repo)

        assert result is None


class TestParseModuleConfidence:
    """Tests for parse_module_confidence end-to-end."""

    def test_high_confidence(self, tmp_repo: Path) -> None:
        """5+ test functions -> high confidence."""
        test_file = tmp_repo / "tests" / "vizier" / "tools" / "test_engines.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "\n".join(f"def test_case_{i}(): pass" for i in range(6)) + "\n"
        )

        result = parse_module_confidence("vizier/tools/engines.py", tmp_repo)

        assert result == ModuleConfidence(
            source_path="vizier/tools/engines.py",
            test_path=str(test_file),
            test_count=6,
            confidence="high",
        )

    def test_none_confidence(self, tmp_repo: Path) -> None:
        """No test file -> none confidence."""
        result = parse_module_confidence("vizier/tools/missing.py", tmp_repo)

        assert result == ModuleConfidence(
            source_path="vizier/tools/missing.py",
            test_path=None,
            test_count=0,
            confidence="none",
        )

    def test_low_confidence(self, tmp_repo: Path) -> None:
        """Test file exists but has 0 test functions -> low confidence."""
        test_file = tmp_repo / "tests" / "vizier" / "adapter" / "test_empty.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# empty test file\nimport pytest\n")

        result = parse_module_confidence("vizier/adapter/empty.py", tmp_repo)

        assert result == ModuleConfidence(
            source_path="vizier/adapter/empty.py",
            test_path=str(test_file),
            test_count=0,
            confidence="low",
        )

    def test_medium_confidence(self, tmp_repo: Path) -> None:
        """1-4 test functions -> medium confidence."""
        test_file = tmp_repo / "tests" / "vizier" / "adapter" / "test_some.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def test_one(): pass\ndef test_two(): pass\n")

        result = parse_module_confidence("vizier/adapter/some.py", tmp_repo)

        assert result == ModuleConfidence(
            source_path="vizier/adapter/some.py",
            test_path=str(test_file),
            test_count=2,
            confidence="medium",
        )
