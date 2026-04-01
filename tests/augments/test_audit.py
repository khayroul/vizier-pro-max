"""Tests for augments/sandbox/audit.py — post-execution audit logger."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from augments.sandbox.audit import record


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database path."""
    return tmp_path / "test_audit.db"


class TestRecordCreation:
    """Audit records should be correctly stored in SQLite."""

    def test_record_creates_entry(self, db_path: Path) -> None:
        record(
            code="print('hello')",
            exit_code=0,
            duration_ms=42.5,
            files_touched=["output/result.txt"],
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute("SELECT * FROM code_audit").fetchall()
        assert len(rows) == 1

    def test_all_fields_populated(self, db_path: Path) -> None:
        code = "x = 1 + 2"
        record(
            code=code,
            exit_code=0,
            duration_ms=15.3,
            files_touched=["output/a.txt", "tmp/b.txt"],
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM code_audit").fetchone()

        expected_hash = hashlib.sha256(code.encode()).hexdigest()
        assert row["code_hash"] == expected_hash
        assert row["code_preview"] == code
        assert row["exit_code"] == 0
        assert row["duration_ms"] == pytest.approx(15.3)
        assert "output/a.txt" in row["files_touched_json"]
        assert "tmp/b.txt" in row["files_touched_json"]
        assert row["timestamp"] > 0

    def test_code_preview_truncated_at_500(self, db_path: Path) -> None:
        long_code = "x" * 1000
        record(
            code=long_code,
            exit_code=0,
            duration_ms=1.0,
            files_touched=[],
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT code_preview FROM code_audit").fetchone()
        assert len(row["code_preview"]) == 500

    def test_table_auto_created(self, db_path: Path) -> None:
        """First call to record should create the table."""
        assert not db_path.exists()
        record(
            code="pass",
            exit_code=0,
            duration_ms=0.5,
            files_touched=[],
            db_path=db_path,
        )
        assert db_path.exists()
        with sqlite3.connect(str(db_path)) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        table_names = [t[0] for t in tables]
        assert "code_audit" in table_names

    def test_multiple_records(self, db_path: Path) -> None:
        for idx in range(3):
            record(
                code=f"step_{idx}",
                exit_code=idx,
                duration_ms=float(idx),
                files_touched=[],
                db_path=db_path,
            )
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM code_audit").fetchone()[0]
        assert count == 3


class TestRecordFailureHandling:
    """Audit record should log warning and not raise on DB errors."""

    def test_sqlite_error_suppressed(self, db_path: Path) -> None:
        """When sqlite3.connect raises sqlite3.Error, record() logs and returns."""
        with patch(
            "augments.sandbox.audit.sqlite3.connect",
            side_effect=sqlite3.OperationalError("disk I/O error"),
        ):
            # Should not raise
            record(
                code="print('boom')",
                exit_code=0,
                duration_ms=1.0,
                files_touched=[],
                db_path=db_path,
            )

    def test_os_error_suppressed(self, db_path: Path) -> None:
        """When mkdir raises OSError, record() logs and returns."""
        with patch(
            "augments.sandbox.audit.Path.mkdir",
            side_effect=OSError("permission denied"),
        ):
            # Should not raise
            record(
                code="print('boom')",
                exit_code=0,
                duration_ms=1.0,
                files_touched=[],
                db_path=db_path,
            )
