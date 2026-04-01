"""Competitive analysis — data load -> pandas analysis -> chart -> LLM narrative."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from adapter.llm_client import chat as llm_chat
from scripts.research.analyze_data import run as analyze_run
from scripts.research.render_chart import run as chart_run

logger = structlog.get_logger(__name__)


def _generate_narrative(topic: str, data_summary: str) -> str:
    """Call LLM for narrative analysis (OpenAI -> Ollama fallback)."""
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a market analyst. Given competitive data, "
                    "write a concise analysis with key findings and "
                    "recommendations. Use markdown formatting."
                ),
            },
            {
                "role": "user",
                "content": f"Topic: {topic}\n\nData summary:\n{data_summary}",
            },
        ],
        max_tokens=1024,
    )
    return result or f"## {topic}\n\nData summary:\n```\n{data_summary}\n```\n"


def run(
    *,
    topic: str,
    data_path: str | None = None,
    output_dir: str = "output/reports",
) -> dict[str, Any]:
    """Run competitive analysis on a topic with optional data.

    Args:
        topic: Analysis topic or question.
        data_path: Path to CSV with competitor data.
        output_dir: Directory for output artifacts (chart, report).

    Returns:
        Dict with report, chart_path (if data provided), and status.
    """
    if not topic.strip():
        msg = "topic must not be empty"
        raise ValueError(msg)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    chart_path: str | None = None
    data_summary = ""

    if data_path:
        data_file = Path(data_path)
        if not data_file.exists():
            msg = f"Data file not found: {data_path}"
            raise FileNotFoundError(msg)

        # Step 1: Analyze data
        analysis = analyze_run(input_path=data_path, operation="describe")
        data_summary = analysis["summary"]

        # Step 2: Generate chart
        summary_data = json.loads(data_summary)
        columns = list(summary_data.keys())
        if len(columns) >= 2:
            chart_output = str(out / "analysis_chart.png")
            try:
                chart_result = chart_run(
                    chart_type="bar",
                    data={"labels": columns[:10], "values": list(range(len(columns[:10])))},
                    output_path=chart_output,
                    title=f"Competitive Analysis: {topic[:50]}",
                )
                chart_path = chart_result["file_path"]
                logger.info("Chart generated: %s", chart_path)
            except (ValueError, KeyError) as exc:
                logger.warning("Chart generation failed: %s", exc)

    # Step 3: Generate narrative via LLM
    report = _generate_narrative(topic, data_summary or "No data provided.")

    # Step 4: Write report
    report_path = out / "report.md"
    report_content = report
    if chart_path:
        report_content += f"\n\n![Analysis Chart]({chart_path})\n"
    report_path.write_text(report_content, encoding="utf-8")

    result: dict[str, Any] = {
        "report": report,
        "report_path": str(report_path),
        "status": "completed",
    }
    if chart_path:
        result["chart_path"] = chart_path

    logger.info("Competitive analysis complete: %s", topic[:50])
    return result
