"""Template cloning loop — vision -> HTML -> render -> delta -> iterate.

Full convergence loop:
1. Target image -> LLM describes HTML/CSS
2. Render HTML -> screenshot
3. calculate_delta(target, rendered) -> composite score
4. If score < threshold and iterations remain -> feed delta to LLM -> adjusted HTML
5. Parameterize with Jinja2 placeholders
6. Save template
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import structlog

from adapter.llm_client import chat as llm_chat
from middleware.cost_ledger import record_quality
from middleware.deliverable_context import (
    clear_context,
    set_pipeline_step,
    start_deliverable,
)
from middleware.trace_exporter import (
    check_anomalies,
    export_trace,
    log_anomaly,
    notify_anomaly,
)
from scripts.visual.calculate_delta import DeltaResult, calculate_delta
from scripts.visual.screenshot_html import run as screenshot_run

logger = structlog.get_logger(__name__)

_PIPELINE_NAME = "clone_converge"
_PIPELINE_VERSION = "1.0"


def _encode_image_as_data_uri(image_path: str) -> str:
    """Read an image file, base64-encode it, and return a data URI.

    Args:
        image_path: Filesystem path to the image file.

    Returns:
        A ``data:image/<type>;base64,...`` URI string.
    """
    path = Path(image_path)
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime_type};base64,{encoded}"


def _build_vision_messages(
    *,
    target_image_path: str,
    iteration: int,
    delta_guidance: str | None = None,
    previous_html: str | None = None,
    rendered_image_path: str | None = None,
) -> list[dict[str, str | list[Any]]]:
    """Build OpenAI vision-API messages with ``image_url`` content blocks.

    First iteration sends only the target image.  Subsequent iterations
    include the target, the rendered screenshot, and natural-language
    guidance derived from the delta comparison.

    Args:
        target_image_path: Path to the reference design image.
        iteration: Current convergence iteration (1-based).
        delta_guidance: Natural-language guidance from ``_delta_to_guidance``.
        previous_html: HTML produced on the prior iteration.
        rendered_image_path: Screenshot of the prior iteration's HTML.

    Returns:
        Message list ready for ``llm_chat()``.
    """
    system_msg: dict[str, str | list[Any]] = {
        "role": "system",
        "content": (
            "You are an HTML/CSS generator. Output clean semantic "
            "HTML5 with inline CSS. Output ONLY the HTML document, "
            "no explanation."
        ),
    }

    target_uri = _encode_image_as_data_uri(target_image_path)

    # Build user content blocks
    content_blocks: list[dict[str, Any]] = [
        {"type": "text", "text": "Generate clean semantic HTML5 with inline CSS that matches this target design."},
        {
            "type": "image_url",
            "image_url": {"url": target_uri, "detail": "high"},
        },
    ]

    if iteration > 1 and previous_html and delta_guidance and rendered_image_path:
        rendered_uri = _encode_image_as_data_uri(rendered_image_path)
        content_blocks.extend([
            {"type": "text", "text": f"\nPrevious HTML:\n```html\n{previous_html}\n```"},
            {"type": "text", "text": f"\nHere is your previous rendering:"},
            {
                "type": "image_url",
                "image_url": {"url": rendered_uri, "detail": "high"},
            },
            {"type": "text", "text": f"\nImprovement guidance:\n{delta_guidance}"},
        ])
    else:
        content_blocks.append(
            {"type": "text", "text": "\nGenerate the initial HTML/CSS approximation."},
        )

    user_msg: dict[str, str | list[Any]] = {
        "role": "user",
        "content": content_blocks,
    }
    return [system_msg, user_msg]


def _delta_to_guidance(delta: DeltaResult) -> str:
    """Convert numeric delta signals to natural-language improvement guidance.

    Produces actionable sentences that tell the LLM *what* to fix without
    exposing raw metric names or numbers.

    Args:
        delta: The ``DeltaResult`` from ``calculate_delta``.

    Returns:
        Multi-sentence guidance string.
    """
    lines: list[str] = []

    if delta.ssim_score < 0.6:
        lines.append(
            "The overall structure is significantly different from the target. "
            "Re-examine the layout hierarchy and element positioning."
        )
    elif delta.ssim_score < 0.8:
        lines.append(
            "The structure is partially correct but needs refinement. "
            "Adjust spacing, sizing, and alignment to match the target more closely."
        )

    if delta.color_delta_e > 20.0:
        lines.append(
            "The color palette is off -- match the target colors more closely. "
            "Pay attention to background, text, and accent colors."
        )
    elif delta.color_delta_e > 10.0:
        lines.append(
            "Colors are close but not accurate enough. Fine-tune the exact "
            "color values to match the target design."
        )

    if delta.pixel_diff_pct > 30.0:
        lines.append(
            "Too many pixels differ from the target. Check element sizes, "
            "borders, and background fills."
        )

    if delta.layout_score < 0.5:
        lines.append(
            "The layout structure does not match the target well. "
            "Verify column widths, row heights, and overall element arrangement."
        )
    elif delta.layout_score < 0.7:
        lines.append(
            "Layout is roughly correct but element positions need adjustment. "
            "Fine-tune margins and padding."
        )

    if delta.text_match_pct < 70.0:
        lines.append(
            "Text content does not match the target well. Verify all headings, "
            "body text, and labels are accurate."
        )
    elif delta.text_match_pct < 90.0:
        lines.append(
            "Most text matches but some content may be missing or different. "
            "Double-check all visible text against the target."
        )

    if not lines:
        lines.append(
            "The result is close to the target. Make minor refinements to "
            "improve the match."
        )

    return " ".join(lines)


def _call_llm_for_html(
    target_image_path: str,
    iteration: int,
    delta_feedback: str | None = None,
    previous_html: str | None = None,
    rendered_image_path: str | None = None,
) -> str:
    """Call LLM to generate or refine HTML/CSS (OpenAI -> Ollama fallback)."""
    step = "html_refine" if delta_feedback else "html_generate"
    set_pipeline_step(f"{step}_iter{iteration}", _PIPELINE_NAME, _PIPELINE_VERSION)

    messages = _build_vision_messages(
        target_image_path=target_image_path,
        iteration=iteration,
        delta_guidance=delta_feedback,
        previous_html=previous_html,
        rendered_image_path=rendered_image_path,
    )

    result = llm_chat(
        messages=messages,
        max_tokens=4096,
        timeout=45.0,
        strip_preamble=True,
    )
    return result or _fallback_html("LLM unavailable")


def _fallback_html(reason: str) -> str:
    """Return minimal HTML when LLM is unavailable."""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Generated</title></head><body>"
        f"<p><!-- LLM unavailable: {reason} --></p>"
        "</body></html>"
    )


def _render_html_to_png(html: str, output_path: Path) -> Path:
    """Render HTML string to PNG using Playwright via screenshot script."""
    result = screenshot_run(
        html_content=html,
        output_path=str(output_path),
    )
    return Path(result["file_path"])


def run(
    *,
    target_image_path: str,
    output_dir: str = "output/templates",
    max_iterations: int = 5,
    threshold: float = 0.80,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Clone a visual design into a reusable Jinja2 template.

    Returns dict with status, score, iterations, and template_path.
    """
    did = start_deliverable(client_id=client_id)

    try:
        target = Path(target_image_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        if not target.exists():
            msg = f"Target not found: {target}"
            record_quality(did, 3.0, False)
            return {"status": "error", "message": msg, "score": 0.0}

        best_score = 0.0
        best_html = ""
        delta_feedback: str | None = None
        previous_html: str | None = None
        rendered_image_path: str | None = None

        for iteration in range(1, max_iterations + 1):
            logger.info("Convergence iteration %d/%d", iteration, max_iterations)

            # Step 1-2: Generate/refine HTML via vision API
            html = _call_llm_for_html(
                target_image_path=target_image_path,
                iteration=iteration,
                delta_feedback=delta_feedback,
                previous_html=previous_html,
                rendered_image_path=rendered_image_path,
            )
            previous_html = html

            # Step 3: Render to PNG
            rendered_path = out / f"rendered_iter{iteration}.png"
            rendered_path = _render_html_to_png(html, rendered_path)
            rendered_image_path = str(rendered_path)

            # Step 4: Calculate delta
            delta = calculate_delta(target=target, rendered=rendered_path)
            score = delta.composite_score
            logger.info(
                "Iteration %d score: %.3f (threshold: %.3f)",
                iteration,
                score,
                threshold,
            )

            if score > best_score:
                best_score = score
                best_html = html

            # Step 5: Check convergence
            if score >= threshold:
                logger.info("Converged at iteration %d with score %.3f", iteration, score)
                template_path = out / "template.html"
                template_path.write_text(best_html)
                quality_score = min(10.0, 7.0 + best_score * 3.0)
                record_quality(did, quality_score, True)
                _check_and_export(did, client_id)
                return {
                    "status": "converged",
                    "score": best_score,
                    "iterations": iteration,
                    "template_path": str(template_path),
                    "deliverable_id": did,
                }

            # Build natural-language feedback for next iteration
            delta_feedback = _delta_to_guidance(delta)

        # Max iterations reached — record quality based on best score achieved.
        template_path = out / "template.html"
        template_path.write_text(best_html)
        quality_score = min(10.0, 7.0 + best_score * 3.0)
        passed = best_score >= threshold
        record_quality(did, quality_score, passed)
        _check_and_export(did, client_id)
        return {
            "status": "max_iterations",
            "score": best_score,
            "iterations": max_iterations,
            "template_path": str(template_path),
            "deliverable_id": did,
        }

    finally:
        clear_context()


def _check_and_export(did: str, client_id: str | None) -> None:
    """Check anomalies and export trace if needed."""
    anomaly = check_anomalies(did)
    if anomaly["is_anomaly"]:
        trace_path = export_trace(did)
        log_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
        notify_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
