"""Content Generate Pipeline — Brief -> RAG -> Copy -> Formatted Output.

Gate 1: Validates brief, generates content (stub), renders PDF if requested.
Gate 2+: Adds full RAG retrieval, LLM generation, quality scoring.
Session 2: JSON-structured output, quality gates via run_with_gates.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import structlog

from adapter.llm_client import chat as llm_chat
from middleware.cost_ledger import record_quality
from middleware.deliverable_context import (
    clear_context,
    get_client_id,
    get_deliverable_id,
    set_pipeline_step,
    start_deliverable,
)
from middleware.pipeline_runner import run_with_gates
from middleware.trace_exporter import (
    check_anomalies,
    export_trace,
    log_anomaly,
    notify_anomaly,
)
from scripts.document.render_typst import render_to_pdf

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ContentResponse:
    """Structured fields from LLM content generation response."""

    title: str
    body: str
    hashtags: list[str]


def _extract_structured_response(response: str) -> ContentResponse:
    """Parse LLM JSON response into structured fields. Single parse.

    Args:
        response: Raw LLM response text (JSON or plain text).

    Returns:
        ContentResponse with title, body, and hashtags extracted.
    """
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            return ContentResponse(
                title=str(data.get("title", "")),
                body=str(data.get("body", "")),
                hashtags=[str(t) for t in data.get("hashtags", []) if t],
            )
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: extract from plain text
    title = _extract_title_from_response(response)
    return ContentResponse(title=title, body=response, hashtags=[])


_PIPELINE_NAME = "content_generate"
_PIPELINE_VERSION = "2.0"

_SYSTEM_PROMPT = (
    "You are Vizier, a content creation assistant for Malaysian SMEs. "
    "Output ONLY valid JSON with these exact keys:\n"
    '{"title": "...", "body": "...", "hashtags": ["...", "..."]}\n\n'
    "Rules:\n"
    "- title: A compelling headline (max 10 words)\n"
    "- body: The full post content in markdown. Professional but warm tone.\n"
    "- hashtags: 3-5 relevant hashtags\n"
    "- No preamble, no sign-off, no offers to revise\n"
    "- Target audience and platform conventions should match the brief"
)

_INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "brief": {"type": "string", "required": True},
}

_OUTPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "content": {"type": "string", "required": True},
    "format": {"type": "string", "required": True},
}


def _call_llm(brief: str, client_id: str | None = None) -> str | None:
    """Call LLM for content generation (OpenAI -> Ollama fallback)."""
    set_pipeline_step("llm_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
    prompt = f"Generate social media content based on this brief:\n\n{brief}"
    if client_id:
        prompt += f"\n\nClient: {client_id}"

    return llm_chat(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        strip_preamble=True,
    )


def _extract_title_from_response(response: str) -> str:
    """Extract a title from the LLM response.

    Tries JSON parse first, then markdown heading, then first sentence.

    Args:
        response: Raw LLM response text.

    Returns:
        Extracted title string.
    """
    # Try JSON parse
    try:
        data = json.loads(response)
        if isinstance(data, dict) and "title" in data:
            return str(data["title"])
    except (json.JSONDecodeError, ValueError):
        pass

    # Try markdown heading
    heading_match = re.match(r"^#\s+(.+)", response.strip())
    if heading_match:
        return heading_match.group(1).strip()

    # Fall back to first sentence
    first_line = response.strip().split("\n")[0]
    sentence_match = re.match(r"^(.+?[.!?])", first_line)
    if sentence_match:
        return sentence_match.group(1).strip()

    return first_line[:80].strip()


def _extract_body_from_response(response: str) -> str:
    """Extract the body content from the LLM response.

    Tries JSON parse first (body + hashtags), then returns raw text.

    Args:
        response: Raw LLM response text.

    Returns:
        Extracted body string.
    """
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            body = str(data.get("body", ""))
            hashtags = data.get("hashtags", [])
            if isinstance(hashtags, list) and hashtags:
                body += "\n\n" + " ".join(str(tag) for tag in hashtags)
            return body
    except (json.JSONDecodeError, ValueError):
        pass

    return response


def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
    """Core pipeline logic called by run_with_gates.

    Args:
        inputs: Dict with ``brief``, optional ``client_id`` and ``output_format``.

    Returns:
        Dict with ``content``, ``format``, ``brief``, and optional pdf fields.
    """
    brief: str = inputs["brief"]
    client_id: str | None = inputs.get("client_id")
    output_format: str = inputs.get("output_format", "markdown")

    if not brief.strip():
        return {"error": "Brief cannot be empty", "content": "", "format": output_format}

    # Call LLM via Hermes proxy; fall back to stub if unavailable.
    is_stub = False
    raw_content = _call_llm(brief, client_id)
    if raw_content is None:
        raw_content = f"[Generated content for: {brief[:100]}]"
        is_stub = True

    # Extract structured fields from the response (single parse)
    parsed = _extract_structured_response(raw_content)
    content = parsed.body

    result: dict[str, Any] = {
        "content": content,
        "format": output_format,
        "brief": brief,
    }

    if client_id:
        result["client_id"] = client_id

    # PDF rendering — typst compile
    if output_format == "pdf":
        set_pipeline_step("pdf_render", _PIPELINE_NAME, _PIPELINE_VERSION)
        pdf_result = render_to_pdf(
            content=content,
            title=parsed.title,
            accent_color="2563eb",
            hashtags=parsed.hashtags if parsed.hashtags else None,
        )

        if "error" in pdf_result:
            logger.warning("PDF rendering failed: %s", pdf_result["error"])
            result["pdf_error"] = pdf_result["error"]
        else:
            result["pdf_path"] = pdf_result["pdf_path"]
            logger.info("PDF rendered: %s", pdf_result["pdf_path"])

    # Record quality via property-based scorer.
    from middleware.quality_scorer import score_content_generate  # noqa: PLC0415

    did = get_deliverable_id()
    if did:
        score = score_content_generate(
            content=content,
            title=parsed.title,
            pdf_path=result.get("pdf_path"),
            hashtags=parsed.hashtags,
        )
        record_quality(did, score.score, score.passed)

    return result


def run(
    brief: str,
    client_id: str | None = None,
    output_format: str = "markdown",
) -> dict[str, Any]:
    """Execute the content generation pipeline with quality gates.

    Args:
        brief: Content brief describing what to produce.
        client_id: Client ID for brand context loading.
        output_format: Output format — "markdown", "pdf", or "html".

    Returns:
        Dict with generated content, metadata, and quality_report.
        If output_format is "pdf", includes ``pdf_path``.
    """
    did = start_deliverable(client_id=client_id)

    try:
        inputs: dict[str, Any] = {"brief": brief, "output_format": output_format}
        if client_id is not None:
            inputs["client_id"] = client_id

        result = run_with_gates(
            pipeline_fn=_pipeline_fn,
            inputs=inputs,
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            pipeline_name=_PIPELINE_NAME,
        )

        # Check for anomalies; export trace if found.
        _check_and_export(did, client_id)

        logger.info(
            "Content pipeline completed: format=%s, brief_len=%d",
            output_format,
            len(brief),
        )
        return {**result, "deliverable_id": did}

    finally:
        clear_context()


def _check_and_export(did: str, client_id: str | None) -> None:
    """Check anomalies and export trace if needed."""
    anomaly = check_anomalies(did)
    if anomaly["is_anomaly"]:
        trace_path = export_trace(did)
        log_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
        notify_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
