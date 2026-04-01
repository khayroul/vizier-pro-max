"""Search Wisdom Vault via LightRAG.

Uses LightRAG in-process with local storage. Falls back gracefully
if LightRAG is not installed or KG_VAULT_PATH is not configured.
"""
from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_VALID_MODES = {"hybrid", "local", "global"}


def _get_rag_instance() -> Any | None:
    """Initialize LightRAG instance from KG_VAULT_PATH, or None if unavailable."""
    vault_path = os.environ.get("KG_VAULT_PATH")
    if not vault_path:
        logger.debug("KG_VAULT_PATH not set, RAG search unavailable")
        return None

    try:
        from lightrag import LightRAG, QueryParam  # type: ignore[import-untyped]  # noqa: F401

        rag = LightRAG(working_dir=vault_path)
        return rag
    except ImportError:
        logger.warning("lightrag package not installed, RAG search unavailable")
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Failed to initialize LightRAG: %s", exc)
        return None


def run(*, query: str, mode: str = "hybrid") -> dict[str, Any]:
    """Search the knowledge base.

    Args:
        query: Search query string. Must not be empty.
        mode: LightRAG search mode — "hybrid", "local", or "global".

    Returns:
        Dict with results list and mode. Results is empty list if RAG unavailable.
    """
    if not query.strip():
        msg = "query must not be empty"
        raise ValueError(msg)

    if mode not in _VALID_MODES:
        msg = f"Invalid mode: {mode!r}. Valid: {sorted(_VALID_MODES)}"
        raise ValueError(msg)

    logger.info("RAG search: query='%s', mode='%s'", query[:50], mode)

    rag = _get_rag_instance()
    if rag is None:
        return {
            "results": [],
            "mode": mode,
            "status": "unavailable",
            "reason": "LightRAG not configured (set KG_VAULT_PATH)",
        }

    try:
        from lightrag import QueryParam  # type: ignore[import-untyped]

        result = rag.query(query, param=QueryParam(mode=mode))

        # LightRAG returns a string; wrap in list for consistent interface
        results = [result] if isinstance(result, str) else list(result)
        logger.info("RAG returned %d results", len(results))
        return {
            "results": results,
            "mode": mode,
            "status": "ok",
        }
    except (ImportError, OSError, ValueError) as exc:
        logger.warning("RAG query failed: %s", exc)
        return {
            "results": [],
            "mode": mode,
            "status": "error",
            "reason": str(exc),
        }
