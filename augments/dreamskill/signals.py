"""Extract signals from structlog traces for memory consolidation."""
from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that indicate corrections, preferences, decisions
_CORRECTION = re.compile(
    r"(?:no|don't|not|stop|never)\s+(?:use|do|make|add)",
    re.IGNORECASE,
)
_PREFERENCE = re.compile(
    r"(?:I prefer|always use|should be|must be)",
    re.IGNORECASE,
)
_DECISION = re.compile(
    r"(?:decided|decision|we'll go with|let's use)",
    re.IGNORECASE,
)
_PATTERN = re.compile(
    r"(?:every time|always|whenever|each time)",
    re.IGNORECASE,
)
_SIGNAL_PATTERNS = [
    (_CORRECTION, "correction", "high"),
    (_PREFERENCE, "preference", "high"),
    (_DECISION, "decision", "medium"),
    (_PATTERN, "pattern", "medium"),
]


def extract_signals(*, db_path: Path) -> list[dict[str, Any]]:
    """Scan prompt_log for correction/preference/decision signals."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT session_id, timestamp, result FROM prompt_log "
        "WHERE result IS NOT NULL ORDER BY timestamp"
    ).fetchall()
    conn.close()

    signals: list[dict[str, Any]] = []
    for session_id, timestamp, result in rows:
        for pattern, signal_type, confidence in _SIGNAL_PATTERNS:
            if pattern.search(result):
                signals.append({
                    "fact": result.strip(),
                    "date": timestamp,
                    "confidence": confidence,
                    "type": signal_type,
                    "session_id": session_id,
                })
                break  # One signal per log entry

    logger.info("Extracted %d signals from prompt_log", len(signals))
    return signals
