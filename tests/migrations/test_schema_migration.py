"""Tests for Gate 4 Track 1 schema migration."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def _combined_migration_sql() -> str:
    parts: list[str] = []
    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        parts.append(migration_path.read_text())
    return "\n".join(parts)


@pytest.fixture()
def db_with_prompt_log(tmp_path: Path) -> Path:
    """Create a DB with the existing prompt_log table (Gate 1 schema)."""
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO prompt_log (task_id, step, model, timestamp) VALUES (?, ?, ?, ?)",
        ["task_1", 1, "gpt-5.4-mini", 1000.0],
    )
    conn.commit()
    conn.close()
    return db_path


def _apply_migration(db_path: Path) -> None:
    sql = _combined_migration_sql()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql)
    conn.commit()
    conn.close()


class TestSchemaMigration:
    def test_migration_file_exists(self) -> None:
        assert (MIGRATIONS_DIR / "001_cost_ledger.sql").exists()
        assert (MIGRATIONS_DIR / "002_llm_metering_metadata.sql").exists()

    def test_creates_cost_ledger_table(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "cost_ledger" in tables

    def test_cost_ledger_has_pipeline_name_column(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(cost_ledger)").fetchall()]
        conn.close()
        assert "pipeline_name" in columns
        assert "step_name" in columns
        assert "provider_name" in columns
        assert "status" in columns

    def test_creates_anomaly_log_table(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "anomaly_log" in tables

    def test_adds_deliverable_id_to_prompt_log(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(prompt_log)").fetchall()]
        conn.close()
        assert "deliverable_id" in columns

    def test_existing_prompt_log_rows_preserved(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        row = conn.execute("SELECT task_id, deliverable_id FROM prompt_log WHERE task_id = ?", ["task_1"]).fetchone()
        conn.close()
        assert row[0] == "task_1"
        assert row[1] is None

    def test_deliverable_summary_view_exists(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
        conn.close()
        assert "deliverable_summary" in views
