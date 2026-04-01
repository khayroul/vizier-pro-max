"""Tests for DeerFlow shared_memory."""
from __future__ import annotations

from pathlib import Path

from augments.deerflow.shared_memory import SharedMemory


class TestSharedMemory:
    def test_write_and_read(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-123", base_dir=tmp_path)
        mem.write("child-1", {"observation": "Market is growing"})
        data = mem.read_all()
        assert len(data) == 1
        assert data[0]["observation"] == "Market is growing"

    def test_multiple_writes(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-456", base_dir=tmp_path)
        mem.write("child-1", {"obs": "A"})
        mem.write("child-2", {"obs": "B"})
        data = mem.read_all()
        assert len(data) == 2

    def test_cleanup(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-789", base_dir=tmp_path)
        mem.write("child-1", {"obs": "test"})
        assert mem.file_path.exists()
        mem.cleanup()
        assert not mem.file_path.exists()

    def test_read_empty(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-empty", base_dir=tmp_path)
        data = mem.read_all()
        assert data == []
