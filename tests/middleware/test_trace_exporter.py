"""Tests for anomaly detection and trace export."""
from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from middleware.deliverable_context import clear_context

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
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
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def traces_dir(tmp_path: Path) -> Path:
    d = tmp_path / "traces"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _patch(db_path: Path, traces_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setattr("middleware.trace_exporter.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.trace_exporter.TRACES_DIR", str(traces_dir))
    clear_context()
    yield
    clear_context()


def _insert_cost(db_path: Path, deliverable_id: str, **overrides: object) -> None:
    defaults = {
        "client_id": "client_1", "pipeline_name": "content_generate",
        "step_name": "draft", "model": "gpt-5.4-mini",
        "input_tokens": 100, "output_tokens": 50,
        "prompt_text": '{"role":"user"}', "response_text": "resp",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, pipeline_name, step_name, model,
            input_tokens, output_tokens, prompt_text, response_text, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [deliverable_id, defaults["client_id"], defaults["pipeline_name"],
         defaults["step_name"], defaults["model"], defaults["input_tokens"],
         defaults["output_tokens"], defaults["prompt_text"],
         defaults["response_text"], time.time()],
    )
    conn.commit()
    conn.close()


def _insert_quality(db_path: Path, deliverable_id: str, score: float) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO quality_results (deliverable_id, quality_score, all_gates_passed, timestamp) VALUES (?, ?, ?, ?)",
        [deliverable_id, score, 1 if score >= 7.0 else 0, time.time()],
    )
    conn.commit()
    conn.close()


def _insert_baseline(db_path: Path, pipeline: str, avg: float, stddev: float) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO cost_baselines (pipeline_name, avg_cost, stddev, sample_count, updated_at) VALUES (?, ?, ?, ?, ?)",
        [pipeline, avg, stddev, 20, time.time()],
    )
    conn.commit()
    conn.close()


class TestCheckAnomalies:
    def test_detects_low_quality(self, db_path: Path) -> None:
        from middleware.trace_exporter import check_anomalies
        _insert_cost(db_path, "d-low-q")
        _insert_quality(db_path, "d-low-q", 5.0)
        result = check_anomalies("d-low-q")
        assert result["is_anomaly"] is True
        assert any("quality" in r.lower() for r in result["reasons"])

    def test_detects_high_cost(self, db_path: Path) -> None:
        from middleware.trace_exporter import check_anomalies
        _insert_baseline(db_path, "content_generate", avg=100.0, stddev=10.0)
        _insert_cost(db_path, "d-high-c", input_tokens=500, output_tokens=500)
        _insert_quality(db_path, "d-high-c", 8.0)
        result = check_anomalies("d-high-c")
        assert result["is_anomaly"] is True
        assert any("cost" in r.lower() for r in result["reasons"])

    def test_no_anomaly_when_normal(self, db_path: Path) -> None:
        from middleware.trace_exporter import check_anomalies
        _insert_baseline(db_path, "content_generate", avg=150.0, stddev=50.0)
        _insert_cost(db_path, "d-ok")
        _insert_quality(db_path, "d-ok", 8.0)
        result = check_anomalies("d-ok")
        assert result["is_anomaly"] is False


class TestExportTrace:
    def test_exports_json_file(self, db_path: Path, traces_dir: Path) -> None:
        from middleware.trace_exporter import export_trace
        _insert_cost(db_path, "d-export")
        path = export_trace("d-export")
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["deliverable_id"] == "d-export"
        assert len(data["steps"]) > 0
        assert "model" in data["steps"][0]
        assert "prompt_text" in data["steps"][0]


class TestLogAnomaly:
    def test_records_anomaly_in_db(self, db_path: Path) -> None:
        from middleware.trace_exporter import log_anomaly
        log_anomaly("d-anom", "client_1", "content_generate", ["quality too low"], "/traces/d-anom.json")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM anomaly_log WHERE deliverable_id = ?", ["d-anom"]).fetchone()
        conn.close()
        assert row is not None
        assert "quality" in json.loads(row["reasons_json"])[0].lower()
