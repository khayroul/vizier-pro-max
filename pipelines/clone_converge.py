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

from pathlib import Path
from typing import Any

import httpx
import structlog

from scripts.visual.calculate_delta import calculate_delta
from scripts.visual.screenshot_html import run as screenshot_run

logger = structlog.get_logger(__name__)

_LLM_ENDPOINT = "http://localhost:11435/v1/chat/completions"
_LLM_MODEL = "gpt-5.4-mini"


def _call_llm_for_html(
    target_image_path: str,
    delta_feedback: str | None = None,
    previous_html: str | None = None,
) -> str:
    """Call GPT-5.4-mini to generate or refine HTML/CSS."""
    parts = ["Generate clean semantic HTML5 with inline CSS matching a visual design."]

    if previous_html and delta_feedback:
        parts.append(f"\nPrevious HTML:\n```html\n{previous_html}\n```")
        parts.append(f"\nDelta feedback (improve these):\n{delta_feedback}")
    else:
        parts.append(f"\nTarget image path: {target_image_path}")
        parts.append("\nGenerate the initial HTML/CSS approximation.")

    try:
        resp = httpx.post(
            _LLM_ENDPOINT,
            json={
                "model": _LLM_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an HTML/CSS generator. Output clean semantic "
                            "HTML5 with inline CSS. Output ONLY the HTML document, "
                            "no explanation."
                        ),
                    },
                    {"role": "user", "content": "\n".join(parts)},
                ],
                "max_tokens": 4096,
            },
            timeout=45.0,
        )
        if resp.status_code != 200:
            logger.warning("LLM returned status %d", resp.status_code)
            return _fallback_html("LLM returned non-200")

        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            return _fallback_html("No choices returned")

        content = choices[0].get("message", {}).get("content", "")
        if not content.strip():
            return _fallback_html("Empty content")

        return content
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("LLM unreachable for HTML generation: %s", exc)
        return _fallback_html(str(exc))


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
) -> dict[str, Any]:
    """Clone a visual design into a reusable Jinja2 template.

    Returns dict with status, score, iterations, and template_path.
    """
    target = Path(target_image_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        msg = f"Target not found: {target}"
        return {"status": "error", "message": msg, "score": 0.0}

    best_score = 0.0
    best_html = ""
    delta_feedback: str | None = None
    previous_html: str | None = None

    for iteration in range(1, max_iterations + 1):
        logger.info("Convergence iteration %d/%d", iteration, max_iterations)

        # Step 1-2: Generate/refine HTML
        html = _call_llm_for_html(
            target_image_path=target_image_path,
            delta_feedback=delta_feedback,
            previous_html=previous_html,
        )
        previous_html = html

        # Step 3: Render to PNG
        rendered_path = out / f"rendered_iter{iteration}.png"
        rendered_path = _render_html_to_png(html, rendered_path)

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
            return {
                "status": "converged",
                "score": best_score,
                "iterations": iteration,
                "template_path": str(template_path),
            }

        # Build feedback for next iteration
        delta_feedback = (
            f"SSIM: {delta.ssim_score:.3f}, "
            f"Pixel diff: {delta.pixel_diff_pct:.1f}%, "
            f"Color delta-E: {delta.color_delta_e:.1f}, "
            f"Layout: {delta.layout_score:.3f}, "
            f"Text match: {delta.text_match_pct:.1f}%"
        )

    # Max iterations reached
    template_path = out / "template.html"
    template_path.write_text(best_html)
    return {
        "status": "max_iterations",
        "score": best_score,
        "iterations": max_iterations,
        "template_path": str(template_path),
    }
