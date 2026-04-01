"""Tests for synthetic session generator — DSPy training data bootstrap."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.bootstrap.generate_synthetic_sessions import (
    TRAINING_SCHEMA,
    generate_synthetic_sessions,
    load_templates,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "bootstrap" / "synthetic_sessions.yaml"

EXPECTED_COLUMNS = {
    "session_id",
    "timestamp",
    "input_message",
    "task_type",
    "toolset_chosen",
    "pipeline_used",
    "tool_calls",
    "success",
    "synthetic",
}


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return a temporary database path for test isolation."""
    return tmp_path / "prompt_log.db"


@pytest.fixture()
def populated_db(db_path: Path) -> Path:
    """Generate synthetic sessions into a temp database and return path."""
    generate_synthetic_sessions(
        config_path=CONFIG_PATH,
        db_path=db_path,
        seed=42,
    )
    return db_path


class TestLoadTemplates:
    """Tests for template loading from YAML."""

    def test_loads_all_task_types(self) -> None:
        templates = load_templates(CONFIG_PATH)
        assert "task_types" in templates
        assert len(templates["task_types"]) == 4

    def test_loads_placeholders(self) -> None:
        templates = load_templates(CONFIG_PATH)
        assert "placeholders" in templates
        assert "domain" in templates["placeholders"]


class TestGenerateSyntheticSessions:
    """Tests for the synthetic session generator."""

    def test_produces_at_least_200_rows(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        count = conn.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0]
        conn.close()
        assert count >= 200

    def test_all_task_types_represented(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        task_types = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT task_type FROM training_sessions"
            ).fetchall()
        }
        conn.close()
        expected = {
            "task_classification",
            "template_selection",
            "tool_routing",
            "outline_generation",
        }
        assert task_types == expected

    def test_synthetic_flag_set_on_all_rows(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        non_synthetic = conn.execute(
            "SELECT COUNT(*) FROM training_sessions WHERE synthetic != 1"
        ).fetchone()[0]
        conn.close()
        assert non_synthetic == 0

    def test_deterministic_with_same_seed(self, db_path: Path) -> None:
        generate_synthetic_sessions(
            config_path=CONFIG_PATH, db_path=db_path, seed=123
        )
        conn = sqlite3.connect(db_path)
        rows_a = conn.execute(
            "SELECT session_id, input_message FROM training_sessions ORDER BY session_id"
        ).fetchall()
        conn.close()
        db_path.unlink()

        generate_synthetic_sessions(
            config_path=CONFIG_PATH, db_path=db_path, seed=123
        )
        conn = sqlite3.connect(db_path)
        rows_b = conn.execute(
            "SELECT session_id, input_message FROM training_sessions ORDER BY session_id"
        ).fetchall()
        conn.close()

        assert rows_a == rows_b

    def test_rows_match_expected_schema(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        cursor = conn.execute("PRAGMA table_info(training_sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert columns == EXPECTED_COLUMNS

    def test_task_type_counts_match_config(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        counts = dict(
            conn.execute(
                "SELECT task_type, COUNT(*) FROM training_sessions GROUP BY task_type"
            ).fetchall()
        )
        conn.close()
        assert counts["task_classification"] == 80
        assert counts["template_selection"] == 50
        assert counts["tool_routing"] == 40
        assert counts["outline_generation"] == 30

    def test_session_ids_are_unique(self, populated_db: Path) -> None:
        conn = sqlite3.connect(populated_db)
        total = conn.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0]
        unique = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM training_sessions"
        ).fetchone()[0]
        conn.close()
        assert total == unique

    def test_training_schema_constant_matches(self) -> None:
        assert "session_id" in TRAINING_SCHEMA
        assert "synthetic" in TRAINING_SCHEMA
