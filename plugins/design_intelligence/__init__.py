"""Design Intelligence plugin — palette/font and reference lookup tools."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from plugins.design_intelligence.search_engine import BM25Index, load_csv
from references.query import (
    search_chart_patterns,
    search_quarto_layouts,
    search_report_layouts,
    search_ui_styles,
    search_ux_guidelines,
    warm_reference_query_indices,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"

_SEARCH_FIELDS = ["name", "mood", "tags"]

# Module-level indexes, loaded once at registration
_palette_index: BM25Index | None = None
_font_index: BM25Index | None = None

SEARCH_PALETTES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Search query — mood keywords, content description, or style terms. "
                "Examples: 'warm artistic evening jazz', 'corporate clean minimal', "
                "'vibrant tropical summer'"
            ),
        },
    },
    "required": ["query"],
}

SEARCH_FONTS_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Search query — style terms, mood, or use-case. "
                "Examples: 'elegant creative musical', 'bold modern tech', "
                "'clean professional corporate'"
            ),
        },
    },
    "required": ["query"],
}


def _build_query_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": description,
            },
        },
        "required": ["query"],
    }


SEARCH_UI_STYLES_SCHEMA = _build_query_schema(
    "Search query for UI style families and visual motifs, e.g. 'swiss saas dashboard' or 'retro brutalist landing page'."
)
SEARCH_UX_GUIDELINES_SCHEMA = _build_query_schema(
    "Search query for UX problems, platforms, or best practices, e.g. 'smooth scroll navigation web' or 'form validation mobile'."
)
SEARCH_CHART_PATTERNS_SCHEMA = _build_query_schema(
    "Search query for chart families, analytic goals, or data stories, e.g. 'time series growth line' or 'category comparison ranking'."
)
SEARCH_REPORT_LAYOUTS_SCHEMA = _build_query_schema(
    "Search query for report layout, figure/table conventions, or long-form structure, e.g. 'figure width pdf report' or 'modular typst longform'."
)
SEARCH_QUARTO_LAYOUTS_SCHEMA = _build_query_schema(
    "Search query for Quarto-derived layout, publishing, or callout patterns, e.g. 'collapsible dark mode callout' or 'book project html pdf'."
)


def _handle_reference_search(
    args: dict[str, Any],
    search_fn: Any,
) -> str:
    query = str(args.get("query", ""))
    results = search_fn(query)
    return json.dumps(results, default=str)


def _handle_search_palettes(args: dict[str, Any], agent: Any) -> str:
    """Search palette database and return top 5 matches."""
    if _palette_index is None:
        return json.dumps({"error": "palette index not loaded"})
    query = str(args.get("query", ""))
    results = _palette_index.search(query, top_k=5)
    return json.dumps(results)


def _handle_search_fonts(args: dict[str, Any], agent: Any) -> str:
    """Search font database and return top 5 matches."""
    if _font_index is None:
        return json.dumps({"error": "font index not loaded"})
    query = str(args.get("query", ""))
    results = _font_index.search(query, top_k=5)
    return json.dumps(results)


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader to register design search tools."""
    global _palette_index, _font_index  # noqa: PLW0603

    palettes_path = _DATA_DIR / "palettes.csv"
    fonts_path = _DATA_DIR / "fonts.csv"

    palette_rows = load_csv(palettes_path)
    font_rows = load_csv(fonts_path)

    _palette_index = BM25Index(palette_rows, _SEARCH_FIELDS)
    _font_index = BM25Index(font_rows, _SEARCH_FIELDS)

    logger.info(
        "Design intelligence loaded: %d palettes, %d fonts",
        len(palette_rows),
        len(font_rows),
    )
    reference_counts = warm_reference_query_indices()
    logger.info("Reference corpus lookups loaded: %s", reference_counts)

    ctx.register_tool(
        name="search_palettes",
        toolset="vizier-visual",
        schema=SEARCH_PALETTES_SCHEMA,
        handler=lambda args, **kw: _handle_search_palettes(args, None),
        check_fn=lambda: True,
        description=(
            "Search the design palette database by mood, style, or content keywords. "
            "Returns top 5 matching color palettes with hex values and mood tags. "
            "Call this BEFORE generate_poster to select colors."
        ),
    )

    ctx.register_tool(
        name="search_fonts",
        toolset="vizier-visual",
        schema=SEARCH_FONTS_SCHEMA,
        handler=lambda args, **kw: _handle_search_fonts(args, None),
        check_fn=lambda: True,
        description=(
            "Search the typography database by style, mood, or use-case keywords. "
            "Returns top 5 font pairings with weight and spacing specs. "
            "Call this BEFORE generate_poster to select typography."
        ),
    )

    ctx.register_tool(
        name="search_ui_styles",
        toolset="vizier-visual",
        schema=SEARCH_UI_STYLES_SCHEMA,
        handler=lambda args, **kw: _handle_reference_search(args, search_ui_styles),
        check_fn=lambda: True,
        description=(
            "Search local UI style references from UI UX Pro Max, enriched with "
            "visual motifs. Returns top 5 matches from pinned local corpora only."
        ),
    )

    ctx.register_tool(
        name="search_ux_guidelines",
        toolset="vizier-visual",
        schema=SEARCH_UX_GUIDELINES_SCHEMA,
        handler=lambda args, **kw: _handle_reference_search(args, search_ux_guidelines),
        check_fn=lambda: True,
        description=(
            "Search local UX do/don't guidance from the normalized UI UX Pro Max "
            "corpus. Returns top 5 matching issues, recommendations, and anti-patterns."
        ),
    )

    ctx.register_tool(
        name="search_chart_patterns",
        toolset="vizier-visual",
        schema=SEARCH_CHART_PATTERNS_SCHEMA,
        handler=lambda args, **kw: _handle_reference_search(args, search_chart_patterns),
        check_fn=lambda: True,
        description=(
            "Search local chart references across UI UX Pro Max heuristics and "
            "Vega-Lite example patterns. Reference only; does not invoke a chart runtime."
        ),
    )

    ctx.register_tool(
        name="search_report_layouts",
        toolset="vizier-document",
        schema=SEARCH_REPORT_LAYOUTS_SCHEMA,
        handler=lambda args, **kw: _handle_reference_search(args, search_report_layouts),
        check_fn=lambda: True,
        description=(
            "Search local report-layout references across Quarto layout options, "
            "table/figure conventions, and long-form structure patterns."
        ),
    )

    ctx.register_tool(
        name="search_quarto_layouts",
        toolset="vizier-document",
        schema=SEARCH_QUARTO_LAYOUTS_SCHEMA,
        handler=lambda args, **kw: _handle_reference_search(args, search_quarto_layouts),
        check_fn=lambda: True,
        description=(
            "Search Quarto-derived layout, publishing, and callout references from "
            "the pinned local corpus. Reference only; Quarto is not executed."
        ),
    )
