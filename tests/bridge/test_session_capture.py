"""Tests for bridge.session_capture."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from bridge.session_capture import prompt_log_row_to_event, sync_prompt_log_to_build_capture
from bridge.build_capture import read_events


def _create_prompt_log_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as connection:
        connection.execute(
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


def test_prompt_log_row_to_event_maps_runtime_capture_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _create_prompt_log_db(db_path)
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO prompt_log (
                task_id, step, model, messages_json, tools_json,
                timestamp, tokens_in, tokens_out, deliverable_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "task-1",
                2,
                "gpt-5.4-mini",
                '[{"role":"user","content":"hello"}]',
                '[{"name":"search_rag"}]',
                1712011200.0,
                100,
                40,
                "deliv-1",
            ),
        )
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM prompt_log").fetchone()

    assert row is not None
    event = prompt_log_row_to_event(row)
    assert event.context_type == "runtime"
    assert event.event_type == "decision_made"
    assert event.source == "vizier"
    assert event.trace_refs == ("prompt_log:1",)
    assert event.metadata["deliverable_id"] == "deliv-1"
    assert event.metadata["tool_names"] == ("search_rag",) or event.metadata["tool_names"] == ["search_rag"]


def test_sync_prompt_log_to_build_capture_persists_only_new_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _create_prompt_log_db(db_path)
    with sqlite3.connect(str(db_path)) as connection:
        connection.executemany(
            """
            INSERT INTO prompt_log (
                task_id, step, model, messages_json, tools_json,
                timestamp, tokens_in, tokens_out, deliverable_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("task-1", 1, "gpt-5.4-mini", "[]", "[]", 1712011200.0, 0, 0, None),
                ("task-1", 2, "gpt-5.4-mini", "[]", "[]", 1712011201.0, 10, 5, None),
            ],
        )

    result = sync_prompt_log_to_build_capture(
        prompt_log_db=db_path,
        state_root=tmp_path / "state",
        after_row_id=0,
    )

    assert result.events_written == 2
    assert result.last_prompt_log_id == 2
    assert len(read_events(state_root=tmp_path / "state")) == 2

    second = sync_prompt_log_to_build_capture(
        prompt_log_db=db_path,
        state_root=tmp_path / "state",
        after_row_id=result.last_prompt_log_id,
    )

    assert second.events_written == 0
    assert second.last_prompt_log_id == 2


def test_sync_prompt_log_marks_invalid_json_as_degraded(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _create_prompt_log_db(db_path)
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO prompt_log (
                task_id, step, model, messages_json, tools_json,
                timestamp, tokens_in, tokens_out, deliverable_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("task-1", 1, "gpt-5.4-mini", "{not json", "[]", 1712011200.0, 0, 0, None),
        )

    sync_prompt_log_to_build_capture(
        prompt_log_db=db_path,
        state_root=tmp_path / "state",
        after_row_id=0,
    )

    [event] = read_events(state_root=tmp_path / "state")
    assert event.status == "degraded"
    assert "parse_errors" in event.metadata
