"""Integration tests for sandbox: guard + audit + plugin working together."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from augments.sandbox.audit import record
from augments.sandbox.guard import check
from plugins.sandbox_plugin import post_tool_call, pre_tool_call


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database path."""
    return tmp_path / "integration_audit.db"


class TestSafeCodeFlow:
    """Safe code passes guard and audit records the execution."""

    def test_safe_code_guard_passes_and_audit_records(self, db_path: Path) -> None:
        code = "result = 2 + 2"
        guard_result = check(code)
        assert guard_result.allowed

        record(
            code=code,
            exit_code=0,
            duration_ms=10.0,
            files_touched=[],
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM code_audit").fetchone()[0]
        assert count == 1


class TestBlockedCodeFlow:
    """Blocked code is rejected by guard and rejection is recorded."""

    def test_subprocess_rejected_and_audit_records(self, db_path: Path) -> None:
        code = "import subprocess\nsubprocess.run(['ls'])"
        guard_result = check(code)
        assert not guard_result.allowed

        # Record the rejection in audit
        record(
            code=code,
            exit_code=-1,
            duration_ms=0.0,
            files_touched=[],
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM code_audit").fetchone()
        assert row["exit_code"] == -1


class TestOutputDirFlow:
    """Code writing to output/ passes guard."""

    def test_open_output_passes(self) -> None:
        code = "f = open('output/data.csv', 'w')\nf.write('a,b')\nf.close()"
        result = check(code)
        assert result.allowed


class TestBlockedFileAccess:
    """Code writing to disallowed paths is rejected."""

    def test_open_etc_rejected(self) -> None:
        code = "f = open('/etc/shadow', 'r')"
        result = check(code)
        assert not result.allowed


class TestPluginPreToolCall:
    """pre_tool_call hook blocks dangerous code."""

    def test_skip_non_execute_code(self) -> None:
        result = pre_tool_call(tool_name="search", tool_args={"query": "test"})
        assert result is None

    def test_safe_code_returns_none(self) -> None:
        result = pre_tool_call(
            tool_name="execute_code",
            tool_args={"code": "x = 1 + 2"},
        )
        assert result is None

    def test_blocked_code_returns_error(self) -> None:
        result = pre_tool_call(
            tool_name="execute_code",
            tool_args={"code": "import subprocess"},
        )
        assert result is not None
        assert "error" in result

    def test_blocked_code_error_message_descriptive(self) -> None:
        result = pre_tool_call(
            tool_name="execute_code",
            tool_args={"code": "eval('malicious')"},
        )
        assert result is not None
        assert "eval" in result["error"].lower() or "blocked" in result["error"].lower()


class TestPluginPostToolCall:
    """post_tool_call hook skips non-execute_code tools."""

    def test_skip_non_execute_code(self) -> None:
        # Should not raise
        post_tool_call(
            tool_name="search",
            tool_args={"query": "test"},
            result="ok",
        )

    def test_records_execute_code(self, db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "plugins.sandbox_plugin._AUDIT_DB_PATH",
            db_path,
        )
        post_tool_call(
            tool_name="execute_code",
            tool_args={"code": "x = 1"},
            result="ok",
        )
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM code_audit").fetchone()[0]
        assert count == 1
