"""Competitive analysis — market scan → pandas analysis → chart → report.

Gate 2 stub.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def run(
    *,
    topic: str,
    output_dir: str = "output/reports",
) -> dict[str, str]:
    """Run competitive analysis on a topic."""
    logger.info("competitive_analysis stub: topic=%s", topic)
    return {
        "status": "stub",
        "message": "competitive_analysis pipeline not yet implemented",
        "topic": topic,
    }
