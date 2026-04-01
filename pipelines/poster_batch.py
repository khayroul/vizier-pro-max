"""Batch poster production — CSV + template → posters via Jinja2 + Playwright.

Gate 2 stub: returns hardcoded output. Real implementation uses
vizier-visual tools (playwright_screenshot, pillow_process).
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def run(
    *,
    template_path: str | None = None,
    data_path: str | None = None,
    output_dir: str = "output/posters",
) -> dict[str, str | list[str]]:
    """Produce batch posters from template + data."""
    logger.info("poster_batch stub: template=%s data=%s", template_path, data_path)
    return {
        "status": "stub",
        "message": "poster_batch pipeline not yet implemented",
        "output_dir": output_dir,
        "posters": [],
    }
