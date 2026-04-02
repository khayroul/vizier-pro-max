"""Tests for cost ledger lifecycle hook."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from middleware.deliverable_context import clear_context, start_deliverable

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


@pytest.fixture(autouse=True)
def _patch_db(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("middleware.cost_ledger.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.cost_ledger._tables_initialized", False)
    clear_context()
    yield
    clear_context()


class TestPreLLMCallHook:
    def test_inserts_cost_ledger_row(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call

        did = start_deliverable(client_id="client_1")
        pre_llm_call(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5.4-mini",
            step_name="copy_draft",
            pipeline_name="content_generate",
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_ledger WHERE deliverable_id = ?", [did]).fetchone()
        conn.close()
        assert row is not None
        assert row["model"] == "gpt-5.4-mini"
        assert row["client_id"] == "client_1"
        assert row["step_name"] == "copy_draft"
        assert row["pipeline_name"] == "content_generate"

    def test_works_without_deliverable_context(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call

        clear_context()
        pre_llm_call(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-5.4-mini",
        )
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT deliverable_id FROM cost_ledger").fetchone()
        conn.close()
        assert row[0] is None


class TestPostLLMCallHook:
    def test_updates_token_counts_and_latency(self, db_path: Path) -> None:
        from middleware.cost_ledger import post_llm_call, pre_llm_call

        did = start_deliverable()
        pre_llm_call(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-5.4-mini",
        )
        post_llm_call(
            response="hello back",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_ledger WHERE deliverable_id = ?", [did]).fetchone()
        conn.close()
        assert row["input_tokens"] == 10
        assert row["output_tokens"] == 20
        assert row["response_text"] == "hello back"
        assert row["latency_ms"] >= 0


class TestPreLLMCallContextVar:
    def test_reads_step_from_context_var(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call
        from middleware.deliverable_context import set_pipeline_step

        did = start_deliverable()
        set_pipeline_step("rag_retrieve", "content_generate", "1.0")
        pre_llm_call(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5.4-mini",
            # step_name / pipeline_name intentionally omitted — should come from ContextVar
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_ledger WHERE deliverable_id = ?", [did]).fetchone()
        conn.close()
        assert row["step_name"] == "rag_retrieve"
        assert row["pipeline_name"] == "content_generate"


class TestRecordQuality:
    def test_inserts_quality_result(self, db_path: Path) -> None:
        from middleware.cost_ledger import record_quality

        record_quality("d-123", quality_score=8.5, all_gates_passed=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM quality_results WHERE deliverable_id = ?", ["d-123"]).fetchone()
        conn.close()
        assert row["quality_score"] == 8.5
        assert row["all_gates_passed"] == 1

    def test_upserts_on_second_record(self, db_path: Path) -> None:
        """Second call for same deliverable updates in-place — only one row exists."""
        from middleware.cost_ledger import record_quality

        record_quality("d-upsert", quality_score=5.0, all_gates_passed=False)
        record_quality("d-upsert", quality_score=9.0, all_gates_passed=True)
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT quality_score FROM quality_results WHERE deliverable_id = ?",
            ["d-upsert"],
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == 9.0


class TestUpdateBaseline:
    def test_creates_baseline_after_bootstrap(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call, post_llm_call, update_baseline

        for i in range(20):
            did = start_deliverable()
            pre_llm_call(
                messages=[{"role": "user", "content": f"msg {i}"}],
                model="gpt-5.4-mini",
                step_name="draft",
                pipeline_name="content_generate",
                pipeline_version="1.0",
            )
            post_llm_call(
                response=f"resp {i}",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )
            clear_context()

        update_baseline("content_generate", "1.0", bootstrap_count=20)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_baselines WHERE pipeline_name = ?", ["content_generate"]).fetchone()
        conn.close()
        assert row is not None
        assert row["sample_count"] == 20
