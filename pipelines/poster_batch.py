"""Batch poster production — CSV + template -> posters via Jinja2 + Playwright."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from jinja2.sandbox import SandboxedEnvironment

from scripts.visual.screenshot_html import run as screenshot_run

logger = structlog.get_logger(__name__)


def run(
    *,
    template_path: str | None = None,
    data_path: str | None = None,
    output_dir: str = "output/posters",
) -> dict[str, Any]:
    """Produce batch posters from template + CSV data.

    Args:
        template_path: Path to Jinja2 HTML template.
        data_path: Path to CSV file with one row per poster.
        output_dir: Directory for output PNG files.

    Returns:
        Dict with posters list, count, and status keys.
    """
    if not template_path:
        msg = "template_path is required"
        raise ValueError(msg)
    if not data_path:
        msg = "data_path is required"
        raise ValueError(msg)

    tmpl_file = Path(template_path)
    if not tmpl_file.exists():
        msg = f"Template not found: {template_path}"
        raise FileNotFoundError(msg)

    data_file = Path(data_path)
    if not data_file.exists():
        msg = f"Data file not found: {data_path}"
        raise FileNotFoundError(msg)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load template
    template_text = tmpl_file.read_text(encoding="utf-8")
    env = SandboxedEnvironment()
    template = env.from_string(template_text)

    # Load CSV data
    df = pd.read_csv(data_file)
    rows = df.to_dict(orient="records")

    if not rows:
        return {"posters": [], "count": 0, "status": "completed"}

    posters: list[str] = []
    for idx, row in enumerate(rows):
        # Render template with row data
        html = template.render(**row)

        # Screenshot to PNG
        poster_path = str(out / f"poster_{idx:04d}.png")
        result = screenshot_run(
            html_content=html,
            output_path=poster_path,
            viewport_width=800,
            viewport_height=600,
            full_page=False,
        )
        posters.append(result["file_path"])
        logger.info("Poster %d/%d rendered: %s", idx + 1, len(rows), poster_path)

    logger.info("Batch complete: %d posters", len(posters))
    return {
        "posters": posters,
        "count": len(posters),
        "status": "completed",
    }
