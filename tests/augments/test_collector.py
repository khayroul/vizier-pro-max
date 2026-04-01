"""Tests for distillation collector — extract training pairs from prompt_log.db."""
from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

import pytest

from augments.distillation.collector import (
    CollectionResult,
    InsufficientDataError,
    TrainingExample,
    collect,
)

TASK_TYPE_A = "task_classification"
TASK_TYPE_B = "template_selection"


@pytest.fixture()
def populated_db(tmp_path: Path) -> Path:
    """Create a prompt_log.db with 250 rows for task_type_a and 50 for task_type_b."""
    db_path = tmp_path / "prompt_log.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE training_sessions (
            session_id TEXT,
            timestamp REAL,
            input_message TEXT,
            task_type TEXT,
            toolset_chosen TEXT,
            pipeline_used TEXT,
            tool_calls TEXT,
            success INTEGER,
            synthetic INTEGER
        )
    """)
    rng = random.Random(42)
    toolsets = ["search_rag", "code_gen", "template_render", "http_fetch"]

    # 250 rows for TASK_TYPE_A (200 synthetic + 50 real)
    for i in range(250):
        synthetic = 1 if i < 200 else 0
        conn.execute(
            "INSERT INTO training_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"sess-a-{i}",
                1711929600.0 + i * 60,
                f"Classify this task: example {i}",
                TASK_TYPE_A,
                rng.choice(toolsets),
                "pipeline_v1",
                json.dumps(["tool_a", "tool_b"]),
                1 if rng.random() > 0.1 else 0,
                synthetic,
            ),
        )

    # 10 rows for TASK_TYPE_B (all synthetic) — below MIN_EXAMPLES threshold
    for i in range(10):
        conn.execute(
            "INSERT INTO training_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"sess-b-{i}",
                1711929600.0 + i * 60,
                f"Select template for: example {i}",
                TASK_TYPE_B,
                rng.choice(toolsets),
                "pipeline_v2",
                json.dumps(["tool_c"]),
                1,
                1,
            ),
        )

    conn.commit()
    conn.close()
    return db_path


class TestCollectFromPopulatedDB:
    """Test extraction from a populated database."""

    def test_collect_returns_collection_result(self, populated_db: Path) -> None:
        result = collect(task_type=TASK_TYPE_A, db_path=populated_db)
        assert isinstance(result, CollectionResult)
        assert result.total_count == 250

    def test_training_examples_are_dataclass(self, populated_db: Path) -> None:
        result = collect(task_type=TASK_TYPE_A, db_path=populated_db)
        assert len(result.train_set) > 0
        example = result.train_set[0]
        assert isinstance(example, TrainingExample)
        assert isinstance(example.input_text, str)
        assert isinstance(example.expected_output, str)
        assert example.task_type == TASK_TYPE_A
        assert isinstance(example.metadata, dict)


class TestTrainTestSplit:
    """Test that train/test split is 80/20 within tolerance."""

    def test_split_ratio(self, populated_db: Path) -> None:
        result = collect(task_type=TASK_TYPE_A, db_path=populated_db)
        total = len(result.train_set) + len(result.test_set)
        assert total == 250
        train_ratio = len(result.train_set) / total
        assert 0.78 <= train_ratio <= 0.82, f"Train ratio {train_ratio} outside 78-82%"

    def test_split_is_deterministic(self, populated_db: Path) -> None:
        r1 = collect(task_type=TASK_TYPE_A, db_path=populated_db, seed=123)
        r2 = collect(task_type=TASK_TYPE_A, db_path=populated_db, seed=123)
        assert [e.input_text for e in r1.train_set] == [
            e.input_text for e in r2.train_set
        ]

    def test_no_overlap_between_train_and_test(self, populated_db: Path) -> None:
        result = collect(task_type=TASK_TYPE_A, db_path=populated_db)
        train_ids = {e.input_text for e in result.train_set}
        test_ids = {e.input_text for e in result.test_set}
        assert train_ids.isdisjoint(test_ids)


class TestFiltering:
    """Test filtering by task_type."""

    def test_filter_by_task_type(self, populated_db: Path) -> None:
        result = collect(task_type=TASK_TYPE_A, db_path=populated_db)
        for example in result.train_set + result.test_set:
            assert example.task_type == TASK_TYPE_A

    def test_different_task_types_return_different_data(
        self, populated_db: Path
    ) -> None:
        """TASK_TYPE_B has only 50 rows so it should raise InsufficientDataError."""
        with pytest.raises(InsufficientDataError):
            collect(task_type=TASK_TYPE_B, db_path=populated_db)


class TestInsufficientData:
    """Test InsufficientDataError when below MIN_EXAMPLES threshold."""

    def test_raises_on_fewer_than_min(self, populated_db: Path) -> None:
        with pytest.raises(InsufficientDataError, match="50"):
            collect(task_type=TASK_TYPE_B, db_path=populated_db)

    def test_raises_on_nonexistent_task_type(self, populated_db: Path) -> None:
        with pytest.raises(InsufficientDataError):
            collect(task_type="nonexistent_type", db_path=populated_db)


class TestSyntheticFlag:
    """Test that synthetic rows are included by default, excludable via flag."""

    def test_synthetic_included_by_default(self, populated_db: Path) -> None:
        result = collect(task_type=TASK_TYPE_A, db_path=populated_db)
        assert result.total_count == 250  # All 250 rows

    def test_synthetic_excludable(self, populated_db: Path) -> None:
        """Only 50 real rows for TASK_TYPE_A — excluding synthetic still works (50 >= MIN)."""
        result = collect(
            task_type=TASK_TYPE_A,
            db_path=populated_db,
            include_synthetic=False,
        )
        assert result.total_count == 50  # Only the 50 non-synthetic rows

    def test_excluding_synthetic_raises_when_insufficient(self, populated_db: Path) -> None:
        """TASK_TYPE_B has only 10 synthetic rows, 0 real — excluding synthetic leaves 0."""
        with pytest.raises(InsufficientDataError):
            collect(
                task_type=TASK_TYPE_B,
                db_path=populated_db,
                include_synthetic=False,
            )
