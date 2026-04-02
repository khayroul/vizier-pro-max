"""Competitive analysis — data load -> pandas analysis -> chart -> LLM narrative."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import structlog

from adapter.llm_client import chat as llm_chat
from middleware.cost_ledger import record_quality
from middleware.deliverable_context import (
    clear_context,
    set_pipeline_step,
    start_deliverable,
)
from middleware.pipeline_runner import run_with_gates
from middleware.quality_scorer import score_competitive_analysis
from middleware.trace_exporter import (
    check_anomalies,
    export_trace,
    log_anomaly,
    notify_anomaly,
)
from scripts.content.fetch_url import fetch as httpx_fetch
from scripts.research.analyze_data import run as analyze_run
from scripts.research.render_chart import run as chart_run

logger = structlog.get_logger(__name__)

_PIPELINE_NAME = "competitive_analysis"
_PIPELINE_VERSION = "2.0"

_INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "topic": {"type": "string", "required": True},
    "data_path": {"type": "string", "required": False},
    "output_dir": {"type": "string", "required": False},
    "client_id": {"type": "string", "required": False},
}

_OUTPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "report": {"type": "string", "required": True},
    "report_path": {"type": "string", "required": True},
    "status": {"type": "string", "required": True},
    "deliverable_id": {"type": "string", "required": True},
}

_MAX_CHARTS = 3


def _select_analysis_operations(
    topic: str,
    columns: list[str],
) -> list[dict[str, str]]:
    """Ask LLM which analysis operations to run on the dataset.

    Args:
        topic: The analysis topic or question.
        columns: Column names available in the dataset.

    Returns:
        List of operation dicts with keys like operation, group_column,
        agg_column, agg_function. Falls back to describe if LLM fails.
    """
    set_pipeline_step("select_operations", _PIPELINE_NAME, _PIPELINE_VERSION)

    prompt = (
        "You are a data analyst. Given a topic and available columns, "
        "return a JSON array of analysis operations to perform.\n"
        "Each operation must be one of: describe, groupby, filter.\n"
        "For groupby, include: group_column, agg_column, agg_function "
        "(sum, mean, count, min, max).\n"
        "For filter, include: filter_expr.\n"
        "Return ONLY valid JSON, no explanation.\n\n"
        f"Topic: {topic}\n"
        f"Columns: {columns}\n"
    )
    raw = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        strip_preamble=True,
    )

    if raw is None:
        logger.warning("LLM unavailable for operation selection, using describe")
        return [{"operation": "describe"}]

    try:
        ops = json.loads(raw)
        if not isinstance(ops, list) or not ops:
            logger.warning("LLM returned invalid operations format, using describe")
            return [{"operation": "describe"}]
        # Validate each operation has at least the operation key
        valid_operations = {"describe", "groupby", "filter"}
        validated: list[dict[str, str]] = []
        for op in ops:
            if isinstance(op, dict) and op.get("operation") in valid_operations:
                validated.append(op)
        if not validated:
            return [{"operation": "describe"}]
        return validated
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse LLM operations response, using describe")
        return [{"operation": "describe"}]


def _build_chart_data(
    analysis_result: dict[str, Any],
    title: str,
) -> dict[str, Any]:
    """Build chart-ready data from analysis results.

    Extracts real numeric values from the analysis result dict,
    never returning sequential integers as placeholder values.

    Args:
        analysis_result: Dict mapping category names to their values.
            Values can be dicts (nested groupby results) or scalars.
        title: Chart title for context.

    Returns:
        Dict with labels, values, chart_type, and title keys.
    """
    labels: list[str] = []
    values: list[float] = []

    for key, val in analysis_result.items():
        if isinstance(val, dict):
            # Nested groupby result: each sub-key is a label
            for sub_key, sub_val in val.items():
                label = f"{key}: {sub_key}" if len(analysis_result) > 1 else str(sub_key)
                labels.append(label)
                try:
                    values.append(float(sub_val))
                except (ValueError, TypeError):
                    values.append(0.0)
        elif isinstance(val, (int, float)):
            labels.append(str(key))
            values.append(float(val))

    # Determine chart type based on data characteristics
    chart_type = "bar"
    if len(labels) <= 5 and all(v >= 0 for v in values):
        total = sum(values)
        if total > 0 and all(v / total <= 1.0 for v in values):
            chart_type = "pie" if len(labels) <= 6 else "bar"

    return {
        "labels": labels,
        "values": values,
        "chart_type": chart_type,
        "title": title,
    }


def _generate_narrative(topic: str, data_summary: str) -> str:
    """Call LLM for narrative analysis with specific data citations.

    Uses strip_preamble=True to remove conversational framing.

    Args:
        topic: The analysis topic.
        data_summary: JSON string of analysis data.

    Returns:
        Structured markdown report with executive summary, findings,
        and recommendations. Falls back to raw data display on failure.
    """
    set_pipeline_step("narrative_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a market analyst writing a concise data report. "
                    "Structure your response with these sections:\n"
                    "## Executive Summary\n"
                    "## Key Findings\n"
                    "## Recommendations\n\n"
                    "IMPORTANT: Cite specific numbers from the data in every "
                    "finding. Do not use vague language — include percentages, "
                    "counts, or values directly from the data."
                ),
            },
            {
                "role": "user",
                "content": f"Topic: {topic}\n\nData summary:\n{data_summary}",
            },
        ],
        max_tokens=1024,
        strip_preamble=True,
    )
    return result or f"## {topic}\n\nData summary:\n```\n{data_summary}\n```\n"


def _generate_search_urls(topic: str) -> list[str]:
    """Generate 3-5 URLs for competitor research via LLM.

    Args:
        topic: The topic to research competitors for.

    Returns:
        List of URL strings, filtered to http/https only.
    """
    set_pipeline_step("search_url_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
    prompt = (
        f'Given the topic "{topic}", generate 3-5 URLs that would contain '
        "competitor information. Target structured data sources like Google Maps "
        "business listings, Yelp pages, industry directories, or social media "
        "business profiles. Return ONLY a JSON array of URL strings.\n"
        "Do NOT return generic search engine result pages.\n"
        "Focus on: pricing, location, reviews, unique selling points."
    )
    raw = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid JSON arrays of URL strings."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        strip_preamble=True,
    )
    if raw is None:
        return []
    try:
        urls = json.loads(raw)
        if isinstance(urls, list):
            return [str(u) for u in urls if isinstance(u, str) and u.startswith("http")]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _fetch_url(url: str) -> str | None:
    """Fetch a URL via httpx_fetch, returning body text or None.

    Args:
        url: The URL to fetch.

    Returns:
        Body text string on success, None on failure.
    """
    try:
        result = httpx_fetch(url)
        if result.get("status_code") == 200:
            return str(result.get("body", ""))
    except (ValueError, httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("Fetch failed for %s: %s", url, exc)
    return None


def _fetch_and_extract(urls: list[str]) -> list[str]:
    """Fetch URLs and return list of successful page texts.

    Args:
        urls: List of URLs to fetch.

    Returns:
        List of non-empty body text strings from successful fetches.
    """
    texts: list[str] = []
    for url in urls:
        text = _fetch_url(url)
        if text:
            texts.append(text)
    return texts


def _extract_competitors(topic: str, page_texts: list[str]) -> list[dict[str, str]]:
    """Extract structured competitor data from fetched page texts.

    Args:
        topic: The research topic.
        page_texts: List of fetched page body texts to extract from.

    Returns:
        List of competitor dicts, each containing at least a 'name' key.
    """
    set_pipeline_step("competitor_extraction", _PIPELINE_NAME, _PIPELINE_VERSION)
    combined = "\n\n---\n\n".join(page_texts[:5])
    prompt = (
        f"From the following web page content about '{topic}', extract competitor information.\n"
        "Return a JSON array of objects with these keys:\n"
        "name, location, pricing_range, strengths, weaknesses, differentiator\n"
        "Extract at least 3 competitors. Return ONLY valid JSON.\n\n"
        f"Content:\n{combined[:8000]}"
    )
    raw = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        strip_preamble=True,
    )
    if raw is None:
        return []
    try:
        competitors = json.loads(raw)
        if isinstance(competitors, list):
            return [c for c in competitors if isinstance(c, dict) and "name" in c]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
    """Core pipeline logic for competitive analysis.

    Args:
        inputs: Dict with topic, data_path, output_dir, client_id.

    Returns:
        Dict with report, report_path, status, deliverable_id,
        and optional chart_path.
    """
    topic: str = inputs["topic"]
    data_path: str | None = inputs.get("data_path")
    output_dir: str = inputs.get("output_dir", "output/reports")
    client_id: str | None = inputs.get("client_id")

    did = start_deliverable(client_id=client_id)

    try:
        if not topic.strip():
            msg = "topic must not be empty"
            raise ValueError(msg)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        chart_paths: list[str] = []
        data_summary = ""

        if data_path:
            set_pipeline_step("data_analysis", _PIPELINE_NAME, _PIPELINE_VERSION)
            data_file = Path(data_path)
            if not data_file.exists():
                msg = f"Data file not found: {data_path}"
                raise FileNotFoundError(msg)

            # Read columns from CSV for LLM-driven strategy
            df = pd.read_csv(data_file, nrows=0)
            columns = df.columns.tolist()

            # Ask LLM which operations to perform
            operations = _select_analysis_operations(topic, columns)

            # Run each operation and collect results
            all_results: dict[str, Any] = {}
            for op in operations:
                try:
                    analysis = analyze_run(
                        input_path=data_path,
                        operation=op["operation"],
                        group_column=op.get("group_column"),
                        agg_column=op.get("agg_column"),
                        agg_function=op.get("agg_function", "sum"),
                        filter_expr=op.get("filter_expr"),
                    )
                    op_label = op["operation"]
                    if op.get("group_column"):
                        op_label = f"{op['group_column']}_by_{op.get('agg_function', 'sum')}"
                    all_results[op_label] = json.loads(analysis["summary"])
                except (ValueError, KeyError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "Analysis operation failed: %s — %s", op, exc
                    )

            # Build data summary from all results
            if all_results:
                data_summary = json.dumps(all_results, indent=2)
            else:
                # Fall back to describe
                fallback = analyze_run(input_path=data_path, operation="describe")
                data_summary = fallback["summary"]

            # Generate charts from real analysis results (up to _MAX_CHARTS)
            chart_count = 0
            for result_key, result_data in all_results.items():
                if chart_count >= _MAX_CHARTS:
                    break
                if not isinstance(result_data, dict):
                    continue

                chart_data = _build_chart_data(
                    {result_key: result_data},
                    f"{topic[:40]}: {result_key}",
                )
                if not chart_data["labels"]:
                    continue

                chart_output = str(out / f"analysis_chart_{chart_count}.png")
                try:
                    chart_result = chart_run(
                        chart_type=chart_data["chart_type"],
                        data={
                            "labels": chart_data["labels"],
                            "values": chart_data["values"],
                        },
                        output_path=chart_output,
                        title=chart_data["title"],
                    )
                    chart_paths.append(chart_result["file_path"])
                    chart_count += 1
                    logger.info("Chart generated: %s", chart_result["file_path"])
                except (ValueError, KeyError) as exc:
                    logger.warning("Chart generation failed: %s", exc)

        else:
            # WEB RESEARCH FLOW
            set_pipeline_step("web_research", _PIPELINE_NAME, _PIPELINE_VERSION)

            # Step 1: Generate search URLs
            urls = _generate_search_urls(topic)

            # Step 2: Fetch URLs
            page_texts = _fetch_and_extract(urls)

            if len(page_texts) >= 2:
                # Step 3: Extract competitors
                competitors = _extract_competitors(topic, page_texts)

                if competitors:
                    data_summary = json.dumps(competitors, indent=2)

                    # Build chart from competitor pricing
                    pricing_data: dict[str, float] = {}
                    for comp in competitors:
                        name = comp.get("name", "Unknown")
                        price_str = comp.get("pricing_range", "")
                        # Try to extract a number from the pricing string
                        price_match = re.search(r"(\d+(?:\.\d+)?)", price_str)
                        if price_match:
                            pricing_data[name] = float(price_match.group(1))

                    if pricing_data:
                        chart_data = _build_chart_data(
                            {"pricing": pricing_data},
                            f"{topic[:40]}: Pricing Comparison",
                        )
                        if chart_data["labels"]:
                            chart_output = str(out / "pricing_chart.png")
                            try:
                                chart_result = chart_run(
                                    chart_type="bar",
                                    data={
                                        "labels": chart_data["labels"],
                                        "values": chart_data["values"],
                                    },
                                    output_path=chart_output,
                                    title=chart_data["title"],
                                )
                                chart_paths.append(chart_result["file_path"])
                            except (ValueError, KeyError) as exc:
                                logger.warning("Chart generation failed: %s", exc)
                else:
                    data_summary = "No competitor data extracted."
            else:
                # Fallback: LLM-only analysis
                logger.warning("Web research insufficient (< 2 fetches), using LLM-only fallback")
                data_summary = "Based on general knowledge — web research was unavailable."

        # Generate narrative via LLM
        if not data_path:
            # Web research narrative prompt
            set_pipeline_step("narrative_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
            report = llm_chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a competitive intelligence analyst. Structure your report with:\n"
                            "## Executive Summary\n(Market positioning overview)\n"
                            "## Competitor Profiles\n(1 paragraph each, citing specific data)\n"
                            "## Opportunities and Recommendations\n"
                            "IMPORTANT: Cite specific names, prices, and differentiators."
                        ),
                    },
                    {"role": "user", "content": f"Topic: {topic}\n\nCompetitor data:\n{data_summary}"},
                ],
                max_tokens=1024,
                strip_preamble=True,
            )
            if report is None:
                report = f"## {topic}\n\nCompetitor data:\n```\n{data_summary}\n```\n"
            is_stub = report.startswith(f"## {topic}")
        else:
            report = _generate_narrative(topic, data_summary or "No data provided.")
            is_stub = report.startswith(f"## {topic}")

        # Write report
        report_path = out / "report.md"
        report_content = report
        for cp in chart_paths:
            report_content += f"\n\n![Analysis Chart]({cp})\n"
        report_path.write_text(report_content, encoding="utf-8")

        score = score_competitive_analysis(report, [Path(p) for p in chart_paths])
        record_quality(did, score.score, score.passed)
        _check_and_export(did, client_id)

        result: dict[str, Any] = {
            "report": report,
            "report_path": str(report_path),
            "status": "completed",
            "deliverable_id": did,
        }
        if chart_paths:
            result["chart_path"] = chart_paths[0]
            result["chart_paths"] = chart_paths

        logger.info("Competitive analysis complete: %s", topic[:50])
        return result

    finally:
        clear_context()


def run(
    *,
    topic: str,
    data_path: str | None = None,
    output_dir: str = "output/reports",
    client_id: str | None = None,
) -> dict[str, Any]:
    """Run competitive analysis on a topic with optional data.

    Wraps the core pipeline with quality gates (L1 input, L2 output).

    Args:
        topic: Analysis topic or question.
        data_path: Path to CSV with competitor data.
        output_dir: Directory for output artifacts (chart, report).
        client_id: Client identifier for cost tracking.

    Returns:
        Dict with report, chart_path (if data provided), status,
        deliverable_id, and quality_report.
    """
    inputs: dict[str, Any] = {"topic": topic, "output_dir": output_dir}
    if data_path is not None:
        inputs["data_path"] = data_path
    if client_id is not None:
        inputs["client_id"] = client_id

    return run_with_gates(
        pipeline_fn=_pipeline_fn,
        inputs=inputs,
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        pipeline_name=_PIPELINE_NAME,
    )


def _check_and_export(did: str, client_id: str | None) -> None:
    """Check anomalies and export trace if needed."""
    anomaly = check_anomalies(did)
    if anomaly["is_anomaly"]:
        trace_path = export_trace(did)
        log_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
        notify_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
