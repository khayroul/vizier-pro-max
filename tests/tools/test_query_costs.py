"""Tests for query_costs tool."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_with_costs(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
        )
    """)
    sql = MIGRATION_PATH.read_text().replace(
        "ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;", ""
    )
    conn.executescript(sql)

    now = time.time()
    conn.executemany(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, model, pipeline_name, step_name,
            input_tokens, output_tokens, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("d1", "client_a", "gpt-5.4-mini", "content_generate", "draft", 100, 50, now),
            ("d1", "client_a", "gpt-5.4-mini", "content_generate", "format", 20, 10, now),
            ("d2", "client_b", "qwen3.5:9b", "content_generate", "draft", 200, 100, now),
        ],
    )
    conn.execute(
        "INSERT INTO anomaly_log (deliverable_id, client_id, pipeline_name, reasons_json, timestamp) VALUES (?, ?, ?, ?, ?)",
        ["d1", "client_a", "content_generate", '["quality low"]', now],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _patch_db(db_with_costs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.query_costs.DB_PATH", str(db_with_costs))


class TestQueryCosts:
    def test_per_deliverable(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"deliverable_id": "d1"}))
        assert len(result["steps"]) == 2
        assert result["total_tokens"] == 180

    def test_per_client(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"client_id": "client_a"}))
        assert len(result["deliverables"]) == 1

    def test_model_distribution(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"distribution": True}))
        assert "gpt-5.4-mini" in result["models"]
        assert "qwen3.5:9b" in result["models"]

    def test_anomaly_history(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"anomaly_history": True}))
        assert "anomalies" in result
        assert len(result["anomalies"]) == 1

    def test_handles_missing_table(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from tools.query_costs import query_costs
        empty_db = tmp_path / "empty.db"
        sqlite3.connect(str(empty_db)).close()
        monkeypatch.setattr("tools.query_costs.DB_PATH", str(empty_db))
        result = json.loads(query_costs({}))
        assert "error" in result
