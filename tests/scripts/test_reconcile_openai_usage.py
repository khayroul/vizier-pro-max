"""Tests for scripts.bridge.reconcile_openai_usage."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def _create_state_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE cost_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deliverable_id TEXT,
            client_id TEXT,
            session_id TEXT,
            pipeline_name TEXT,
            step_name TEXT,
            pipeline_version TEXT,
            provider_name TEXT,
            source TEXT,
            modality TEXT,
            status TEXT,
            failure_reason TEXT,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            prompt_text TEXT,
            response_text TEXT,
            latency_ms INTEGER DEFAULT 0,
            timestamp REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            step INTEGER,
            model TEXT,
            messages_json TEXT,
            tools_json TEXT,
            timestamp REAL,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_cost(
    conn: sqlite3.Connection,
    *,
    timestamp: float,
    deliverable_id: str | None,
    client_id: str | None,
    session_id: str | None,
    provider_name: str | None,
    source: str | None,
    input_tokens: int,
    output_tokens: int,
    modality: str = "chat",
    status: str = "succeeded",
    model: str = "gpt-5.4-mini",
) -> None:
    conn.execute(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, session_id, pipeline_name, step_name,
            pipeline_version, provider_name, source, modality, status,
            failure_reason, model, input_tokens, output_tokens, prompt_text,
            response_text, latency_ms, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            deliverable_id,
            client_id,
            session_id,
            "content_generate",
            "draft",
            "1.0",
            provider_name,
            source,
            modality,
            status,
            None,
            model,
            input_tokens,
            output_tokens,
            "[]",
            "ok",
            123,
            timestamp,
        ],
    )


def _insert_prompt(
    conn: sqlite3.Connection,
    *,
    timestamp: float,
    task_id: str,
    tokens_in: int,
    tokens_out: int,
) -> None:
    conn.execute(
        """INSERT INTO prompt_log
           (task_id, step, model, messages_json, tools_json, timestamp, tokens_in, tokens_out, deliverable_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [task_id, 1, "gpt-5.4-mini", "[]", "[]", timestamp, tokens_in, tokens_out, None],
    )


@pytest.fixture()
def state_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    conn = sqlite3.connect(str(db_path))

    day1 = 1743465600.0
    day2 = 1743552000.0

    _insert_cost(
        conn,
        timestamp=day1,
        deliverable_id="d-1",
        client_id="client-a",
        session_id="sess-1",
        provider_name="openai",
        source="hermes",
        input_tokens=100,
        output_tokens=50,
    )
    _insert_cost(
        conn,
        timestamp=day1,
        deliverable_id="d-2",
        client_id="client-a",
        session_id=None,
        provider_name="openai",
        source="pipeline",
        input_tokens=30,
        output_tokens=20,
        modality="image_generation",
        model="gpt-image-1",
    )
    _insert_cost(
        conn,
        timestamp=day1,
        deliverable_id=None,
        client_id=None,
        session_id=None,
        provider_name=None,
        source=None,
        input_tokens=90,
        output_tokens=10,
    )
    _insert_cost(
        conn,
        timestamp=day2,
        deliverable_id="d-3",
        client_id="client-b",
        session_id="sess-2",
        provider_name="ollama",
        source="hermes",
        input_tokens=40,
        output_tokens=10,
        model="qwen3.5:9b",
    )

    _insert_prompt(conn, timestamp=day1, task_id="task-1", tokens_in=120, tokens_out=80)
    _insert_prompt(conn, timestamp=day1 + 60, task_id="task-2", tokens_in=70, tokens_out=30)
    _insert_prompt(conn, timestamp=day2, task_id="task-3", tokens_in=40, tokens_out=20)

    conn.commit()
    conn.close()
    return db_path


class TestReconcileUsage:
    def test_builds_reconciliation_report(self, state_db: Path) -> None:
        from scripts.bridge.reconcile_openai_usage import reconcile_usage

        report = reconcile_usage(
            db_path=state_db,
            openai_total_tokens=1000,
            vizier_reported_tokens=50,
        )

        assert report["cost_ledger"]["provider_metered_rows"]["total_tokens"] == 250
        assert report["cost_ledger"]["openai_metered_rows"]["total_tokens"] == 200
        assert report["cost_ledger"]["hermes_metered_rows"]["total_tokens"] == 200
        assert report["cost_ledger"]["lifecycle_only_rows"]["total_tokens"] == 100
        assert report["prompt_log"]["total_tokens"] == 360
        assert report["historical_gap_estimate"]["estimated_unattributed_hermes_tokens"] == 160
        assert report["cost_ledger"]["risk_buckets"]["metered_rows_missing_session_id"] == 1
        assert report["external_comparison"]["gap_openai_minus_metered_openai"] == 800
        assert report["external_comparison"]["remaining_gap_after_hermes_estimate"] == 640

        by_day = {row["day"]: row for row in report["daily_reconciliation"]}
        assert by_day["2025-04-01"]["estimated_unattributed_hermes_tokens"] == 150
        assert by_day["2025-04-02"]["estimated_unattributed_hermes_tokens"] == 10

    def test_handles_missing_database(self, tmp_path: Path) -> None:
        from scripts.bridge.reconcile_openai_usage import reconcile_usage

        report = reconcile_usage(db_path=tmp_path / "missing.db")

        assert "error" in report

    def test_cli_outputs_json(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.bridge.reconcile_openai_usage import main

        exit_code = main(
            [
                "--db-path",
                str(state_db),
                "--json",
                "--openai-total-tokens",
                "1000",
                "--vizier-reported-tokens",
                "50",
            ]
        )

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert exit_code == 0
        assert payload["external_comparison"]["vizier_reported_tokens"] == 50
        assert payload["historical_gap_estimate"]["estimated_unattributed_hermes_tokens"] == 160

    def test_cli_outputs_text_summary(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.bridge.reconcile_openai_usage import main

        exit_code = main(["--db-path", str(state_db)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Estimated unattributed Hermes tokens: 160" in captured.out
        assert "Top daily Hermes blind spots" in captured.out
