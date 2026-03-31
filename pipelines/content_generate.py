"""Content Generate Pipeline — Brief -> RAG -> Copy -> Formatted Output.

Gate 1: Validates brief, produces structured output placeholder.
        Full RAG + LLM integration via Hermes session in Gate 1 integration task.
Gate 2+: Adds RAG retrieval, multi-format output, quality scoring.
"""
from __future__ import annotations

import logging
from typing import Any

from middleware.quality_gate import validate_input

logger = logging.getLogger(__name__)

_INPUT_SCHEMA = {
    "brief": {"type": "string", "required": True},
    "client_id": {"type": "string", "required": False},
    "output_format": {"type": "string", "required": False},
}


def run(
    brief: str,
    client_id: str | None = None,
    output_format: str = "markdown",
) -> dict[str, Any]:
    """Execute the content generation pipeline.

    Args:
        brief: Content brief describing what to produce.
        client_id: Client ID for brand context loading.
        output_format: Output format — "markdown", "pdf", or "html".

    Returns:
        Dict with generated content and metadata.
    """
    # Exclude None optional fields so the type checker does not reject them.
    payload: dict[str, Any] = {"brief": brief, "output_format": output_format}
    if client_id is not None:
        payload["client_id"] = client_id

    validation = validate_input(payload, _INPUT_SCHEMA)
    if not validation.passed:
        return {"error": f"Input validation failed: {validation.errors}"}

    if not brief.strip():
        return {"error": "Brief cannot be empty"}

    # Gate 1 placeholder
    content = f"[Generated content for: {brief[:100]}]"

    result: dict[str, Any] = {
        "content": content,
        "format": output_format,
        "brief": brief,
    }

    if client_id:
        result["client_id"] = client_id

    logger.info(
        "Content pipeline completed: format=%s, brief_len=%d",
        output_format,
        len(brief),
    )
    return result
