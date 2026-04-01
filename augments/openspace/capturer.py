"""Detect repeating tool call chains from prompt_logger traces.

Scans SQLite prompt_log table, groups tool calls by session,
finds common chain patterns that repeat above threshold.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_session_chains(db_path: Path) -> dict[str, list[str]]:
    """Load tool call sequences grouped by session."""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT session_id, tool_name FROM prompt_log "
            "WHERE tool_name IS NOT NULL "
            "ORDER BY session_id, timestamp, id"
        ).fetchall()

    sessions: dict[str, list[str]] = {}
    for session_id, tool_name in rows:
        sessions.setdefault(session_id, []).append(tool_name)
    return sessions


def _extract_ngrams(
    chain: list[str], min_len: int = 2, max_len: int = 5
) -> list[tuple[str, ...]]:
    """Extract all n-grams of length min_len to max_len from a tool chain."""
    ngrams: list[tuple[str, ...]] = []
    for n in range(min_len, min(max_len + 1, len(chain) + 1)):
        for i in range(len(chain) - n + 1):
            ngrams.append(tuple(chain[i : i + n]))
    return ngrams


def _is_subchain(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """Check if short is a contiguous subchain of long."""
    if len(short) >= len(long):
        return False
    short_str = " ".join(short)
    long_str = " ".join(long)
    return short_str in long_str


def detect_repeating_chains(
    *,
    db_path: Path,
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Detect tool call chains that repeat across sessions.

    Args:
        db_path: Path to the SQLite prompt_log database.
        threshold: Minimum number of unique sessions a chain must
            appear in to be reported.

    Returns:
        List of dicts with keys: tools, occurrences, sessions, description.
    """
    sessions = _load_session_chains(db_path)
    if not sessions:
        return []

    # Count n-gram occurrences across sessions
    ngram_sessions: dict[tuple[str, ...], set[str]] = {}
    for session_id, chain in sessions.items():
        seen_in_session: set[tuple[str, ...]] = set()
        for ngram in _extract_ngrams(chain):
            if ngram not in seen_in_session:
                seen_in_session.add(ngram)
                ngram_sessions.setdefault(ngram, set()).add(session_id)

    # Filter by threshold (count unique sessions, not total occurrences)
    repeating: list[dict[str, Any]] = []
    for ngram, session_ids in ngram_sessions.items():
        if len(session_ids) >= threshold:
            repeating.append(
                {
                    "tools": list(ngram),
                    "occurrences": len(session_ids),
                    "sessions": sorted(session_ids),
                    "description": " -> ".join(ngram),
                }
            )

    # Sort by occurrences descending, then by chain length descending
    repeating.sort(key=lambda x: (-x["occurrences"], -len(x["tools"])))

    # Remove subchains if a longer chain covers them
    filtered: list[dict[str, Any]] = []
    seen_tools: set[tuple[str, ...]] = set()
    for chain_info in repeating:
        tools_tuple = tuple(chain_info["tools"])
        is_sub = any(_is_subchain(tools_tuple, existing) for existing in seen_tools)
        if not is_sub:
            filtered.append(chain_info)
            seen_tools.add(tools_tuple)

    logger.info("Detected %d repeating chains (threshold=%d)", len(filtered), threshold)
    return filtered
