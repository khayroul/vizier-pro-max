"""Post-execution logging for execute_code.

Records: code executed (hash + first 500 chars), files touched,
execution duration, exit code.
Writes to SQLite.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_DB_PATH = Path("data/code_audit.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS code_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    code_hash TEXT NOT NULL,
    code_preview TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    files_touched_json TEXT NOT NULL
)
"""


def _ensure_table(db_path: Path) -> None:
    """Create the code_audit table if it does not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(_CREATE_TABLE_SQL)


def record(
    code: str,
    exit_code: int,
    duration_ms: float,
    files_touched: list[str],
    db_path: Path | None = None,
) -> None:
    """Record a code execution event to the audit database.

    Args:
        code: The executed code string.
        exit_code: Process exit code (0 = success, -1 = blocked).
        duration_ms: Execution duration in milliseconds.
        files_touched: List of file paths touched during execution.
        db_path: SQLite database path. Defaults to data/code_audit.db.
    """
    effective_path = db_path or _DEFAULT_DB_PATH
    try:
        _ensure_table(effective_path)
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        code_preview = code[:500]
        files_json = json.dumps(files_touched, ensure_ascii=False)

        with sqlite3.connect(str(effective_path)) as conn:
            conn.execute(
                """INSERT INTO code_audit
                   (timestamp, code_hash, code_preview, exit_code, duration_ms, files_touched_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    time.time(),
                    code_hash,
                    code_preview,
                    exit_code,
                    duration_ms,
                    files_json,
                ],
            )
    except (sqlite3.Error, OSError) as exc:
        logger.warning("audit_record_failed", error=str(exc))
