"""Render HTML content or a local HTML file to PDF via weasyprint."""
from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def run(
    *,
    html_content: str = "",
    input_path: str = "",
    output_path: str,
) -> dict[str, str]:
    """Render HTML to PDF.

    Args:
        html_content: HTML content string to render.
        input_path: Local HTML file path to render instead of html_content.
        output_path: Destination PDF path.

    Returns:
        Dict with ``file_path`` for the generated PDF.
    """
    if not output_path:
        msg = "output_path is required"
        raise ValueError(msg)
    if not html_content and not input_path:
        msg = "html_content or input_path is required"
        raise ValueError(msg)

    from weasyprint import HTML  # type: ignore[import-untyped]

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    document = HTML(filename=input_path) if input_path else HTML(string=html_content)
    document.write_pdf(str(output))
    logger.info("Rendered PDF", output_path=str(output))
    return {"file_path": str(output)}
