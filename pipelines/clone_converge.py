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

import structlog

from scripts.visual.calculate_delta import calculate_delta

logger = structlog.get_logger(__name__)


def _call_llm_for_html(
    target_image_path: str,
    delta_feedback: str | None = None,
    previous_html: str | None = None,
) -> str:
    """Call GPT-5.4-mini to generate or refine HTML/CSS.

    In production: Hermes LLM call with vision.
    Mocked in tests.
    """
    raise NotImplementedError("LLM call not available in this context")


def _render_html_to_png(html: str, output_path: Path) -> Path:
    """Render HTML to PNG using Playwright.

    In production: calls playwright_screenshot.
    Mocked in tests.
    """
    raise NotImplementedError("Playwright not available in this context")


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
