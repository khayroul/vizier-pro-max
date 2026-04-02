"""Design Intelligence plugin — palette + font search tools.

Registers search_palettes and search_fonts tools backed by BM25 search
over bundled CSV data from UI UX Pro Max.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from plugins.design_intelligence.search_engine import BM25Index, load_csv

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

    ctx.register_tool(
        name="search_palettes",
        toolset="vizier-design",
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
        toolset="vizier-design",
        schema=SEARCH_FONTS_SCHEMA,
        handler=lambda args, **kw: _handle_search_fonts(args, None),
        check_fn=lambda: True,
        description=(
            "Search the typography database by style, mood, or use-case keywords. "
            "Returns top 5 font pairings with weight and spacing specs. "
            "Call this BEFORE generate_poster to select typography."
        ),
    )
