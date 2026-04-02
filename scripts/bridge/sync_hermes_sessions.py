"""ETL: Hermes ~/.hermes/state.db → data/prompt_log.db training_sessions.

Reads sessions + messages from the Hermes state database, extracts
training pairs (input_message, toolset, success), and inserts them
into the training_sessions table for DSPy distillation.

Idempotent: skips sessions already present in training_sessions.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_HERMES_DB = Path.home() / ".hermes" / "state.db"
DEFAULT_TRAINING_DB = Path("data/prompt_log.db")

# Mapping from tool names to toolset categories
_TOOLSET_MAP: dict[str, str] = {
    "analyze_data": "vizier-analytics",
    "render_chart": "vizier-analytics",
    "calculate_delta": "vizier-analytics",
    "merge_pdfs": "vizier-document",
    "render_typst": "vizier-document",
    "convert_format": "vizier-document",
    "generate_image": "vizier-visual",
    "process_image": "vizier-visual",
    "screenshot_html": "vizier-visual",
    "search_rag": "vizier-research",
    "web_search": "vizier-research",
    "send_telegram": "vizier-comms",
    "send_whatsapp": "vizier-comms",
    "speak_text": "vizier-comms",
}

# Mapping from toolset to task_type
_TASK_TYPE_MAP: dict[str, str] = {
    "vizier-analytics": "task_classification",
    "vizier-document": "task_classification",
    "vizier-visual": "task_classification",
    "vizier-research": "task_classification",
    "vizier-comms": "task_classification",
    "vizier-fallback": "task_classification",
}


def _classify_toolset(tool_names: list[str]) -> str:
    """Determine the toolset from the tools used in a session.

    Args:
        tool_names: List of tool names invoked during the session.

    Returns:
        Toolset name string.
    """
    toolset_votes: dict[str, int] = {}
    for tool in tool_names:
        toolset = _TOOLSET_MAP.get(tool, "vizier-fallback")
        toolset_votes[toolset] = toolset_votes.get(toolset, 0) + 1

    if not toolset_votes:
        return "vizier-fallback"

    return max(toolset_votes, key=lambda k: toolset_votes[k])


def _classify_task_type(toolset: str) -> str:
    """Map toolset to task_type for training.

    Args:
        toolset: The determined toolset name.

    Returns:
        Task type string.
    """
    return _TASK_TYPE_MAP.get(toolset, "task_classification")


def sync_sessions(
    hermes_db_path: Path = DEFAULT_HERMES_DB,
    training_db_path: Path = DEFAULT_TRAINING_DB,
) -> int:
    """Sync Hermes sessions into training_sessions table.

    Reads all sessions from Hermes state.db, extracts the first user
    message as input_message, collects tool_name values as tool_calls,
    and inserts into training_sessions. Skips sessions already synced.

    Args:
        hermes_db_path: Path to Hermes state.db.
        training_db_path: Path to training prompt_log.db.

    Returns:
        Number of new sessions inserted.
    """
    if not hermes_db_path.exists():
        logger.warning("hermes_db_not_found", path=str(hermes_db_path))
        return 0

    hermes_conn = sqlite3.connect(str(hermes_db_path))
    hermes_conn.row_factory = sqlite3.Row

    training_conn = sqlite3.connect(str(training_db_path))

    # Get already-synced session IDs
    existing_ids: set[str] = set()
    try:
        rows = training_conn.execute(
            "SELECT session_id FROM training_sessions WHERE synthetic = 0"
        ).fetchall()
        existing_ids = {row[0] for row in rows}
    except sqlite3.OperationalError:
        # Table may not exist yet — that's fine, nothing to skip
        pass

    # Read all Hermes sessions
    sessions = hermes_conn.execute(
        "SELECT id, started_at, end_reason FROM sessions"
    ).fetchall()

    inserted = 0

    for session in sessions:
        session_id = session["id"]

        if session_id in existing_ids:
            logger.debug("session_already_synced", session_id=session_id)
            continue

        # Get first user message
        user_msg_row = hermes_conn.execute(
            "SELECT content FROM messages"
            " WHERE session_id = ? AND role = 'user'"
            " ORDER BY timestamp ASC LIMIT 1",
            (session_id,),
        ).fetchone()

        if user_msg_row is None or not user_msg_row["content"]:
            logger.debug("no_user_message", session_id=session_id)
            continue

        input_message = user_msg_row["content"]

        # Collect tool names
        tool_rows = hermes_conn.execute(
            "SELECT tool_name FROM messages"
            " WHERE session_id = ? AND tool_name IS NOT NULL",
            (session_id,),
        ).fetchall()
        tool_names = [row["tool_name"] for row in tool_rows]

        toolset = _classify_toolset(tool_names)
        task_type = _classify_task_type(toolset)
        success = 1 if session["end_reason"] == "completed" else 0
        tool_calls_json = json.dumps(tool_names) if tool_names else "[]"

        training_conn.execute(
            "INSERT INTO training_sessions"
            " (session_id, timestamp, input_message, task_type,"
            "  toolset_chosen, pipeline_used, tool_calls, success, synthetic)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                session_id,
                session["started_at"],
                input_message,
                task_type,
                toolset,
                "hermes_session",
                tool_calls_json,
                success,
            ),
        )
        inserted += 1

    training_conn.commit()
    training_conn.close()
    hermes_conn.close()

    logger.info("sync_complete", inserted=inserted, skipped=len(existing_ids))
    return inserted


def main() -> None:
    """CLI entry point for syncing Hermes sessions."""
    count = sync_sessions()
    logger.info("sync_hermes_complete", sessions_synced=count)


if __name__ == "__main__":  # pragma: no cover
    main()
