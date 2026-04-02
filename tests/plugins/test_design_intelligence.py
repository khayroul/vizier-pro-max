"""Tests for Design Intelligence plugin — BM25 search, hex validation, plugin registration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plugins.design_intelligence.search_engine import (
    BM25Index,
    _tokenize,
    load_csv,
    validate_hex,
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_lowercases(self) -> None:
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_strips_punctuation(self) -> None:
        assert _tokenize("warm, inviting, artistic") == ["warm", "inviting", "artistic"]

    def test_empty_string(self) -> None:
        assert _tokenize("") == []


# ---------------------------------------------------------------------------
# Hex validation
# ---------------------------------------------------------------------------


class TestValidateHex:
    @pytest.mark.parametrize(
        "value",
        ["#FFF", "#fff", "#FFFF", "#aabb00", "#AABBCCDD", "#000", "#123456"],
    )
    def test_valid_hex(self, value: str) -> None:
        assert validate_hex(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "FFF",
            "#GGG",
            "#12",
            "#12345",
            "#1234567",
            "#123456789",
            "rgb(0,0,0)",
            "#",
            "not-a-color",
        ],
    )
    def test_invalid_hex(self, value: str) -> None:
        assert validate_hex(value) is False


# ---------------------------------------------------------------------------
# BM25 search
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_docs() -> list[dict[str, str]]:
    return [
        {"name": "Sunset Warmth", "mood": "warm inviting artistic", "tags": "sunset earthy creative", "primary": "#E07A5F"},
        {"name": "Ocean Breeze", "mood": "cool calm refreshing", "tags": "ocean water serene", "primary": "#2196F3"},
        {"name": "Corporate Trust", "mood": "professional clean corporate", "tags": "business trust formal", "primary": "#2563EB"},
        {"name": "Neon Nights", "mood": "vibrant bold electric", "tags": "neon gaming dark", "primary": "#7C3AED"},
        {"name": "Forest Green", "mood": "natural organic calm", "tags": "nature forest green", "primary": "#059669"},
        {"name": "Luxury Gold", "mood": "premium elegant luxury", "tags": "gold luxury fashion", "primary": "#A16207"},
    ]


class TestBM25Index:
    def test_relevance_ranking(self, sample_docs: list[dict[str, str]]) -> None:
        """Query for 'warm artistic' should rank 'Sunset Warmth' first."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("warm artistic", top_k=3)

        assert len(results) == 3
        assert results[0]["name"] == "Sunset Warmth"
        assert float(results[0]["score"]) > 0

    def test_top_k_limit(self, sample_docs: list[dict[str, str]]) -> None:
        """Returns exactly top_k results."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("calm", top_k=2)
        assert len(results) == 2

    def test_default_top_k_is_five(self, sample_docs: list[dict[str, str]]) -> None:
        """Default top_k is 5."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("calm")
        assert len(results) == 5

    def test_empty_query_fallback(self, sample_docs: list[dict[str, str]]) -> None:
        """Empty query returns first 5 rows as fallback."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("")
        assert len(results) == 5
        assert results[0]["name"] == sample_docs[0]["name"]
        assert float(results[0]["score"]) == 0.0

    def test_no_match_fallback(self, sample_docs: list[dict[str, str]]) -> None:
        """Query with no matching terms returns first 5 rows."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("xyzzyplugh")
        assert len(results) == 5
        assert all(float(r["score"]) == 0.0 for r in results)

    def test_result_has_score_field(self, sample_docs: list[dict[str, str]]) -> None:
        """Each result dict contains a 'score' key."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("luxury gold")
        for result in results:
            assert "score" in result

    def test_result_preserves_all_fields(self, sample_docs: list[dict[str, str]]) -> None:
        """Result dicts include all original fields plus score."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("ocean")
        assert results[0]["primary"] == "#2196F3"

    def test_does_not_mutate_original(self, sample_docs: list[dict[str, str]]) -> None:
        """Search should not mutate the original document dicts."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        index.search("warm")
        assert "score" not in sample_docs[0]

    def test_json_serializable(self, sample_docs: list[dict[str, str]]) -> None:
        """Results must be JSON-serializable."""
        index = BM25Index(sample_docs, ["name", "mood", "tags"])
        results = index.search("corporate professional")
        serialized = json.dumps(results)
        parsed = json.loads(serialized)
        assert len(parsed) > 0
        assert "name" in parsed[0]
        assert "score" in parsed[0]


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


class TestLoadCsv:
    def test_load_palettes(self) -> None:
        """Bundled palettes.csv loads with expected columns."""
        data_dir = Path(__file__).parent.parent.parent / "plugins" / "design_intelligence" / "data"
        rows = load_csv(data_dir / "palettes.csv")
        assert len(rows) == 161
        assert "name" in rows[0]
        assert "primary" in rows[0]
        assert "mood" in rows[0]
        assert "tags" in rows[0]

    def test_load_fonts(self) -> None:
        """Bundled fonts.csv loads with expected columns."""
        data_dir = Path(__file__).parent.parent.parent / "plugins" / "design_intelligence" / "data"
        rows = load_csv(data_dir / "fonts.csv")
        assert len(rows) == 71
        assert "heading_font" in rows[0]
        assert "body_font" in rows[0]
        assert "mood" in rows[0]

    def test_all_palette_hex_values_valid(self) -> None:
        """Every hex color in palettes.csv must pass hex validation."""
        data_dir = Path(__file__).parent.parent.parent / "plugins" / "design_intelligence" / "data"
        rows = load_csv(data_dir / "palettes.csv")
        hex_fields = ["primary", "secondary", "accent", "background", "text"]
        for row in rows:
            for field in hex_fields:
                value = row[field]
                assert validate_hex(value), f"Row '{row['name']}' field '{field}' has invalid hex: {value!r}"


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    def test_registers_lookup_tools(self) -> None:
        """Plugin registers palette/font and reference lookup tools."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        assert ctx.register_tool.call_count == 7
        tool_names = [call[1]["name"] for call in ctx.register_tool.call_args_list]
        assert "search_palettes" in tool_names
        assert "search_fonts" in tool_names
        assert "search_ui_styles" in tool_names
        assert "search_ux_guidelines" in tool_names
        assert "search_chart_patterns" in tool_names
        assert "search_report_layouts" in tool_names
        assert "search_quarto_layouts" in tool_names

    def test_registers_under_visual_toolset(self) -> None:
        """Design search tools should register under visual/document toolsets."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        toolsets = {
            call[1]["name"]: call[1]["toolset"]
            for call in ctx.register_tool.call_args_list
        }
        assert toolsets == {
            "search_palettes": "vizier-visual",
            "search_fonts": "vizier-visual",
            "search_ui_styles": "vizier-visual",
            "search_ux_guidelines": "vizier-visual",
            "search_chart_patterns": "vizier-visual",
            "search_report_layouts": "vizier-document",
            "search_quarto_layouts": "vizier-document",
        }

    def test_visual_reference_tools_are_hidden_in_telegram_assistant_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Telegram assistant mode should gate visual reference tools until work mode is active."""
        from plugins.design_intelligence import register
        from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode

        monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
        clear_telegram_mode()

        ctx = MagicMock()
        register(ctx)

        ui_styles_call = next(
            call[1]
            for call in ctx.register_tool.call_args_list
            if call[1]["name"] == "search_ui_styles"
        )
        assert ui_styles_call["check_fn"]() is False

        set_telegram_mode(platform="telegram", mode="vizier_work")
        assert ui_styles_call["check_fn"]() is True

    def test_tool_schemas_have_query_param(self) -> None:
        """Both tool schemas require a 'query' parameter."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        for call in ctx.register_tool.call_args_list:
            schema = call[1]["schema"]
            assert "query" in schema["properties"]
            assert "query" in schema["required"]

    def test_palette_handler_returns_json(self) -> None:
        """search_palettes handler returns valid JSON with results."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        # Find the palette handler
        palette_call = next(
            c for c in ctx.register_tool.call_args_list
            if c[1]["name"] == "search_palettes"
        )
        handler = palette_call[1]["handler"]
        result_json = handler({"query": "luxury elegant"})
        results = json.loads(result_json)

        assert isinstance(results, list)
        assert len(results) == 5
        assert "primary" in results[0]
        assert "score" in results[0]

    def test_font_handler_returns_json(self) -> None:
        """search_fonts handler returns valid JSON with results."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        font_call = next(
            c for c in ctx.register_tool.call_args_list
            if c[1]["name"] == "search_fonts"
        )
        handler = font_call[1]["handler"]
        result_json = handler({"query": "modern tech"})
        results = json.loads(result_json)

        assert isinstance(results, list)
        assert len(results) == 5
        assert "heading_font" in results[0]
        assert "body_font" in results[0]
        assert "score" in results[0]

    def test_ui_style_handler_returns_json(self) -> None:
        """search_ui_styles handler returns local reference results."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        style_call = next(
            c for c in ctx.register_tool.call_args_list
            if c[1]["name"] == "search_ui_styles"
        )
        handler = style_call[1]["handler"]
        result_json = handler({"query": "swiss saas dashboard"})
        results = json.loads(result_json)

        assert isinstance(results, list)
        assert len(results) == 5
        assert results[0]["dataset_id"] == "ui_styles"
        assert "visual_motif" in results[0]
        assert "score" in results[0]

    def test_quarto_layout_handler_returns_json(self) -> None:
        """search_quarto_layouts handler returns Quarto-derived references."""
        from plugins.design_intelligence import register

        ctx = MagicMock()
        register(ctx)

        quarto_call = next(
            c for c in ctx.register_tool.call_args_list
            if c[1]["name"] == "search_quarto_layouts"
        )
        handler = quarto_call[1]["handler"]
        result_json = handler({"query": "collapsible dark mode callout"})
        results = json.loads(result_json)

        assert isinstance(results, list)
        assert len(results) == 5
        assert results[0]["dataset_id"] == "callout_patterns"
        assert "score" in results[0]
