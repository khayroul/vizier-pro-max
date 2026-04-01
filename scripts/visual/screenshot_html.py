"""Playwright HTML → PNG screenshot wrapper."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _render_with_playwright(
    *,
    html_path: str,
    output_path: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> str:
    """Render HTML file to PNG via Playwright (sync API)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height}
        )
        page.goto(f"file://{html_path}")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path


def run(
    *,
    html_content: str | None = None,
    input_path: str | None = None,
    output_path: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> dict[str, str]:
    """Render HTML to PNG. Provide html_content (string) or input_path (file)."""
    if not html_content and not input_path:
        msg = "Must provide html_content or input_path"
        raise ValueError(msg)
    if html_content:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
        tmp.write(html_content)
        tmp.close()
        html_path = tmp.name
    else:
        html_path = str(Path(input_path).resolve())  # type: ignore[arg-type]
    result_path = _render_with_playwright(
        html_path=html_path, output_path=output_path,
        viewport_width=viewport_width, viewport_height=viewport_height,
    )
    logger.info("Screenshot saved to %s", result_path)
    return {"file_path": result_path}
