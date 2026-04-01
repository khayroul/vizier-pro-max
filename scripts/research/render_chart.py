"""Matplotlib chart generation wrapper."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
import structlog

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt  # noqa: E402

logger = structlog.get_logger(__name__)

_CHART_TYPES = {"bar", "line", "pie", "scatter"}


def run(
    *,
    chart_type: str,
    data: dict[str, Any],
    output_path: str,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
) -> dict[str, str]:
    """Generate a chart and save as PNG.

    Args:
        chart_type: One of "bar", "line", "pie", "scatter".
        data: Chart data dict. Keys vary by chart type:
            bar/pie: "labels" and "values";
            line/scatter: "x" and "y".
        output_path: File path for the output PNG.
        title: Optional chart title.
        xlabel: Optional x-axis label.
        ylabel: Optional y-axis label.

    Returns:
        Dict with "file_path" key pointing to the saved PNG.

    Raises:
        ValueError: If chart_type is not supported.
    """
    if chart_type not in _CHART_TYPES:
        msg = f"Unknown chart_type: {chart_type}. Valid: {sorted(_CHART_TYPES)}"
        raise ValueError(msg)

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        ax.bar(data["labels"], data["values"])
    elif chart_type == "line":
        ax.plot(data["x"], data["y"])
    elif chart_type == "pie":
        ax.pie(data["values"], labels=data["labels"], autopct="%1.1f%%")
    elif chart_type == "scatter":
        ax.scatter(data["x"], data["y"])

    if title:
        ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    fig.tight_layout()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=150)
    plt.close(fig)

    logger.info("Chart saved to %s", output_path)
    return {"file_path": output_path}
