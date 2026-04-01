"""Synthetic session generator for DSPy training data bootstrap.

Loads templates from YAML config, expands placeholders with seeded
randomization, and inserts rows into a SQLite training database.
"""

from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

if TYPE_CHECKING:
    from typing import Any

logger = structlog.get_logger(__name__)

TRAINING_SCHEMA = (
    "session_id TEXT PRIMARY KEY, "
    "timestamp REAL NOT NULL, "
    "input_message TEXT NOT NULL, "
    "task_type TEXT NOT NULL, "
    "toolset_chosen TEXT NOT NULL, "
    "pipeline_used TEXT NOT NULL, "
    "tool_calls TEXT NOT NULL, "
    "success INTEGER NOT NULL, "
    "synthetic INTEGER NOT NULL"
)

CREATE_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS training_sessions ({TRAINING_SCHEMA})"
)


def load_templates(config_path: Path) -> dict[str, Any]:
    """Load synthetic session templates from YAML config.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Parsed YAML as a dictionary with task_types and placeholders.

    Raises:
        FileNotFoundError: If config_path does not exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open("r") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


def _expand_template(
    template_input: str,
    placeholders: dict[str, list[str]],
    rng: random.Random,
) -> str:
    """Replace {placeholder} tokens with random values from word lists.

    Args:
        template_input: Template string with {placeholder} tokens.
        placeholders: Mapping of placeholder names to word lists.
        rng: Seeded random instance for determinism.

    Returns:
        Expanded string with all placeholders filled.
    """
    result = template_input
    for key, values in placeholders.items():
        token = "{" + key + "}"
        while token in result:
            result = result.replace(token, rng.choice(values), 1)
    return result


def _generate_tool_calls(
    task_type: str,
    toolset: str,
    rng: random.Random,
) -> str:
    """Generate a synthetic tool_calls JSON string.

    Args:
        task_type: The type of task being simulated.
        toolset: The toolset name for this session.
        rng: Seeded random instance.

    Returns:
        JSON string representing synthetic tool calls.
    """
    call_count = rng.randint(1, 4)
    calls = [
        {"tool": f"{toolset}.{task_type}_step_{i}", "status": "ok"}
        for i in range(call_count)
    ]
    return json.dumps(calls)


def generate_synthetic_sessions(
    config_path: Path,
    db_path: Path,
    seed: int = 42,
) -> int:
    """Generate synthetic training sessions and insert into SQLite.

    Args:
        config_path: Path to the YAML template config.
        db_path: Path to the SQLite database file.
        seed: Random seed for deterministic generation.

    Returns:
        Number of rows inserted.
    """
    config = load_templates(config_path)
    task_types = config["task_types"]
    placeholders = config["placeholders"]

    rng = random.Random(seed)
    base_timestamp = 1743465600.0  # 2025-04-01 00:00:00 UTC

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    total_inserted = 0

    for task_type_name, task_config in task_types.items():
        count: int = task_config["count"]
        templates: list[dict[str, str]] = task_config["templates"]

        for i in range(count):
            template = templates[i % len(templates)]
            input_message = _expand_template(
                template["input"], placeholders, rng
            )
            toolset = template["toolset"]
            pipeline = template["pipeline"]
            tool_calls = _generate_tool_calls(task_type_name, toolset, rng)

            # Generate deterministic UUID from seed state
            session_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            timestamp = base_timestamp + rng.uniform(0, 86400 * 30)
            success = 1 if rng.random() > 0.05 else 0  # 95% success rate

            conn.execute(
                "INSERT INTO training_sessions "
                "(session_id, timestamp, input_message, task_type, "
                "toolset_chosen, pipeline_used, tool_calls, success, synthetic) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    session_id,
                    timestamp,
                    input_message,
                    task_type_name,
                    toolset,
                    pipeline,
                    tool_calls,
                    success,
                ),
            )
            total_inserted += 1

    conn.commit()
    conn.close()

    logger.info(
        "synthetic_sessions_generated",
        total=total_inserted,
        db_path=str(db_path),
        seed=seed,
    )
    return total_inserted


def main() -> None:
    """CLI entry point for synthetic session generation."""
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "config" / "bootstrap" / "synthetic_sessions.yaml"
    db_path = project_root / "data" / "prompt_log.db"

    count = generate_synthetic_sessions(
        config_path=config_path,
        db_path=db_path,
        seed=42,
    )
    logger.info("generation_complete", rows=count)


if __name__ == "__main__":
    main()
