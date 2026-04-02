"""Integration test — full Track 1 flow.

context → ledger → quality → anomaly → export → query
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from middleware.deliverable_context import clear_context, start_deliverable

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _combined_migration_sql() -> str:
    parts: list[str] = []
    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = migration_path.read_text()
        sql = sql.replace("ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;", "")
        parts.append(sql)
    return "\n".join(parts)


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
    conn.executescript(_combined_migration_sql())
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def traces_dir(tmp_path: Path) -> Path:
    d = tmp_path / "traces"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _patch_all(
    db_path: Path, traces_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("middleware.cost_ledger.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.cost_ledger._tables_initialized", True)
    monkeypatch.setattr("middleware.trace_exporter.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.trace_exporter.TRACES_DIR", str(traces_dir))
    monkeypatch.setattr("tools.query_costs.DB_PATH", str(db_path))
    clear_context()
    yield
    clear_context()


class TestTrack1EndToEnd:
    def test_full_flow(self, db_path: Path, traces_dir: Path) -> None:
        """Pipeline run: cost captured, anomaly checked, trace exported, queryable."""
        from middleware.cost_ledger import post_llm_call, pre_llm_call, record_quality
        from middleware.trace_exporter import check_anomalies, export_trace, log_anomaly
        from tools.query_costs import query_costs

        # 1. Start deliverable
        did = start_deliverable(client_id="acme_corp")

        # 2. Simulate pipeline (2 LLM calls)
        pre_llm_call(
            messages=[{"role": "user", "content": "Write copy"}],
            model="gpt-5.4-mini",
            step_name="draft",
            pipeline_name="content_generate",
            pipeline_version="1.0",
        )
        post_llm_call(
            response="Here is your copy...",
            usage={"prompt_tokens": 150, "completion_tokens": 200},
        )

        pre_llm_call(
            messages=[{"role": "user", "content": "Format"}],
            model="gpt-5.4-mini",
            step_name="format",
            pipeline_name="content_generate",
            pipeline_version="1.0",
        )
        post_llm_call(
            response="Formatted.",
            usage={"prompt_tokens": 50, "completion_tokens": 30},
        )

        # 3. Record quality (low → triggers anomaly)
        record_quality(did, quality_score=5.5, all_gates_passed=False)

        # 4. Check anomalies
        result = check_anomalies(did)
        assert result["is_anomaly"] is True

        # 5. Export trace + log anomaly
        trace_path = export_trace(did)
        log_anomaly(did, "acme_corp", "content_generate", result["reasons"], trace_path)
        trace = json.loads(Path(trace_path).read_text())
        assert len(trace["steps"]) == 2
        assert trace["quality"]["score"] == 5.5

        # 6. Query costs
        breakdown = json.loads(query_costs({"deliverable_id": did}))
        assert breakdown["total_tokens"] == 430

        client = json.loads(query_costs({"client_id": "acme_corp"}))
        assert len(client["deliverables"]) == 1

        anomalies = json.loads(query_costs({"anomaly_history": True}))
        assert len(anomalies["anomalies"]) == 1
