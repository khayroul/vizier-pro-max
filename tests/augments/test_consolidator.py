"""Tests for dream-skill consolidation via structured observational memory."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from augments.dreamskill.consolidator import consolidate
from bridge.build_capture import capture_external_build_event


@pytest.fixture()
def mock_log_db(tmp_path: Path) -> Path:
    """Compatibility fixture for consolidate(db_path=...)."""
    db_path = tmp_path / "prompt_log.db"
    db_path.write_text("", encoding="utf-8")
    return db_path


@pytest.fixture()
def memory_dir(tmp_path: Path) -> Path:
    """Create a memory directory with existing MEMORY.md."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text(
        "- [2026-03-30] Use dark theme for all designs."
        " (confidence: high)\n"
    )
    return mem_dir


class TestConsolidator:
    def test_consolidate_with_qwen_mock(
        self, mock_log_db: Path, memory_dir: Path, tmp_path: Path
    ) -> None:
        """Consolidator derives MEMORY.md from structured evidence."""
        state_root = tmp_path / "state"
        capture_external_build_event(
            source="codex",
            task_id="task-1",
            event_type="verification_run",
            summary="Ran bridge packet verification",
            status="ok",
            timestamp="2026-04-02T12:00:00+00:00",
            state_root=state_root,
            verifications=("python3 -m pytest tests/bridge -q",),
            files_touched=("bridge/watcher.py",),
        )
        capture_external_build_event(
            source="vizier",
            task_id="task-2",
            event_type="failure_seen",
            summary="Runtime capture failed on malformed JSON",
            status="error",
            timestamp="2026-04-02T12:05:00+00:00",
            state_root=state_root,
            files_touched=("plugins/prompt_logger.py",),
        )

        result = consolidate(
            db_path=mock_log_db,
            memory_dir=memory_dir,
            state_root=state_root,
        )

        assert result["status"] == "consolidated"
        memory_content = (memory_dir / "MEMORY.md").read_text()
        assert "Retain workflow" in memory_content
        assert "failure mode" in memory_content.lower()
        assert "dark theme" not in memory_content

    def test_consolidate_falls_back_on_ollama_error(
        self, mock_log_db: Path, memory_dir: Path, tmp_path: Path
    ) -> None:
        """Skips when there is no captured evidence to derive from."""
        result = consolidate(
            db_path=mock_log_db,
            memory_dir=memory_dir,
            state_root=tmp_path / "state",
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "No captured evidence found"

    def test_consolidate_skips_if_recent(
        self, mock_log_db: Path, memory_dir: Path, tmp_path: Path
    ) -> None:
        """Skips if .last-dream is recent (<24h)."""
        (memory_dir / ".last-dream").write_text(str(time.time()))
        capture_external_build_event(
            source="codex",
            task_id="task-1",
            event_type="verification_run",
            summary="Ran bridge packet verification",
            status="ok",
            timestamp="2026-04-02T12:00:00+00:00",
            state_root=tmp_path / "state",
            verifications=("python3 -m pytest tests/bridge -q",),
        )

        result = consolidate(
            db_path=mock_log_db,
            memory_dir=memory_dir,
            state_root=tmp_path / "state",
        )
        assert result["status"] == "skipped"
