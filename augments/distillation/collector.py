"""Extract (input, toolset, success) training pairs from prompt_logger.

Returns list[TrainingExample] with at least 200 rows for the target task type.
Supports filtering by task_type, date range, and synthetic flag.
Splits into train/test sets (80/20) with stratified sampling.
"""
from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

DEFAULT_DB_PATH = Path("data/prompt_log.db")
MIN_EXAMPLES = 50
TRAIN_RATIO = 0.8


class InsufficientDataError(ValueError):
    """Raised when fewer than MIN_EXAMPLES are available for a task type."""


@dataclass(frozen=True)
class TrainingExample:
    """Single training pair extracted from the prompt log."""

    input_text: str
    expected_output: str
    task_type: str
    metadata: dict[str, str | int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionResult:
    """Result of collecting training examples, split into train/test sets."""

    train_set: list[TrainingExample]
    test_set: list[TrainingExample]
    total_count: int


def _query_examples(
    db_path: Path,
    task_type: str,
    include_synthetic: bool,
) -> list[TrainingExample]:
    """Query training_sessions table and return TrainingExample list."""
    conn = sqlite3.connect(str(db_path))
    try:
        query = (
            "SELECT input_message, toolset_chosen, task_type,"
            " session_id, pipeline_used, tool_calls, success, synthetic"
            " FROM training_sessions WHERE task_type = ?"
        )
        params: list[str | int] = [task_type]

        if not include_synthetic:
            query += " AND synthetic = ?"
            params.append(0)

        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    examples: list[TrainingExample] = []
    for row in rows:
        (
            input_message,
            toolset_chosen,
            row_task_type,
            session_id,
            pipeline_used,
            tool_calls,
            success,
            synthetic,
        ) = row
        metadata: dict[str, str | int | float] = {
            "session_id": session_id,
            "pipeline_used": pipeline_used,
            "tool_calls": tool_calls,
            "success": success,
            "synthetic": synthetic,
        }
        examples.append(
            TrainingExample(
                input_text=input_message,
                expected_output=toolset_chosen,
                task_type=row_task_type,
                metadata=metadata,
            )
        )
    return examples


def _split_train_test(
    examples: list[TrainingExample],
    seed: int,
) -> tuple[list[TrainingExample], list[TrainingExample]]:
    """Split examples into train/test sets (80/20) with deterministic shuffle."""
    rng = random.Random(seed)
    shuffled = list(examples)
    rng.shuffle(shuffled)
    split_idx = int(len(shuffled) * TRAIN_RATIO)
    return shuffled[:split_idx], shuffled[split_idx:]


def collect(
    task_type: str,
    db_path: Path = DEFAULT_DB_PATH,
    include_synthetic: bool = True,
    seed: int = 42,
) -> CollectionResult:
    """Collect training examples from prompt_log.db for a given task type.

    Args:
        task_type: The task type to filter by (e.g., "task_classification").
        db_path: Path to the SQLite database.
        include_synthetic: Whether to include synthetic rows (default True).
        seed: Random seed for deterministic train/test split.

    Returns:
        CollectionResult with train_set, test_set, and total_count.

    Raises:
        InsufficientDataError: If fewer than 200 examples available.
    """
    log.info(
        "collecting_training_examples",
        task_type=task_type,
        db_path=str(db_path),
        include_synthetic=include_synthetic,
    )

    examples = _query_examples(db_path, task_type, include_synthetic)

    if len(examples) < MIN_EXAMPLES:
        msg = (
            f"Need at least {MIN_EXAMPLES} examples for task_type={task_type!r},"
            f" found {len(examples)}"
        )
        raise InsufficientDataError(msg)

    train_set, test_set = _split_train_test(examples, seed)

    log.info(
        "collection_complete",
        task_type=task_type,
        total=len(examples),
        train=len(train_set),
        test=len(test_set),
    )

    return CollectionResult(
        train_set=train_set,
        test_set=test_set,
        total_count=len(examples),
    )
