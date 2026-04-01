"""Search Wisdom Vault via LightRAG.

Gate 1: Stub returning placeholder.
Full integration requires LightRAG instance configured with Wisdom Vault path.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def search(query: str, mode: str = "hybrid") -> dict[str, object]:
    """Search the knowledge base.

    Args:
        query: Search query string.
        mode: LightRAG search mode.

    Returns:
        Dict with retrieved context.
    """
    logger.info("RAG search: query='%s', mode='%s'", query[:50], mode)
    return {
        "results": f"[RAG stub: no results for '{query[:50]}' — configure LightRAG]",
        "mode": mode,
    }
