"""Content Generate Pipeline — Brief -> RAG -> Copy -> Formatted Output.

Gate 1: Validates brief, generates content (stub), renders PDF if requested.
Gate 2+: Adds full RAG retrieval, LLM generation, quality scoring.
"""
from __future__ import annotations

import logging
from typing import Any

from middleware.quality_gate import validate_input
from scripts.document.render_typst import render_to_pdf

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
        If output_format is "pdf", includes ``pdf_path``.
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

    # Gate 1: stub content (Gate 2+ replaces with RAG -> LLM)
    content = f"[Generated content for: {brief[:100]}]"

    result: dict[str, Any] = {
        "content": content,
        "format": output_format,
        "brief": brief,
    }

    if client_id:
        result["client_id"] = client_id

    # PDF rendering — typst compile
    if output_format == "pdf":
        title = _extract_title(brief)
        pdf_result = render_to_pdf(content=content, title=title)

        if "error" in pdf_result:
            logger.warning("PDF rendering failed: %s", pdf_result["error"])
            result["pdf_error"] = pdf_result["error"]
        else:
            result["pdf_path"] = pdf_result["pdf_path"]
            logger.info("PDF rendered: %s", pdf_result["pdf_path"])

    logger.info(
        "Content pipeline completed: format=%s, brief_len=%d",
        output_format,
        len(brief),
    )
    return result


def _extract_title(brief: str) -> str:
    """Extract a short title from the brief for the PDF header.

    Args:
        brief: Full brief text.

    Returns:
        Title string (first 50 chars, cleaned).
    """
    first_line = brief.strip().split("\n")[0]
    return first_line[:50].strip()
