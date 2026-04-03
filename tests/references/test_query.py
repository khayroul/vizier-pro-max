"""Tests for normalized reference query helpers."""
from __future__ import annotations

from references.query import (
    REFERENCE_SEARCH_DATASETS,
    search_color_systems,
    search_chart_patterns,
    search_landing_patterns,
    search_quarto_layouts,
    search_report_layouts,
    search_typography_pairings,
    search_ui_styles,
    search_ux_guidelines,
)


def test_reference_search_dataset_map_covers_expected_tools() -> None:
    assert REFERENCE_SEARCH_DATASETS["search_ui_styles"] == (
        ("ui_ux_pro_max", "ui_styles"),
        ("ui_ux_pro_max", "visual_motifs"),
    )
    assert REFERENCE_SEARCH_DATASETS["search_chart_patterns"] == (
        ("ui_ux_pro_max", "chart_usage_patterns"),
        ("vega_lite", "chart_patterns"),
    )
    assert REFERENCE_SEARCH_DATASETS["search_landing_patterns"] == (
        ("ui_ux_pro_max", "landing_patterns"),
    )
    assert REFERENCE_SEARCH_DATASETS["search_typography_pairings"] == (
        ("ui_ux_pro_max", "typography_pairings"),
    )
    assert REFERENCE_SEARCH_DATASETS["search_color_systems"] == (
        ("ui_ux_pro_max", "color_systems"),
    )
    assert REFERENCE_SEARCH_DATASETS["search_quarto_layouts"] == (
        ("quarto", "document_layout_options"),
        ("quarto", "callout_patterns"),
        ("quarto", "publishing_patterns"),
        ("quarto", "longform_structure_patterns"),
    )


def test_search_ui_styles_returns_enriched_style_matches() -> None:
    results = search_ui_styles("swiss saas dashboard")

    assert results
    assert any(result["name"] == "Minimalism & Swiss Style" for result in results)
    first = results[0]
    assert first["dataset_id"] == "ui_styles"
    assert first["reference_family"] == "ui_ux_pro_max"
    assert "visual_motif" in first
    assert first["source_datasets"] == [
        "ui_ux_pro_max/ui_styles",
        "ui_ux_pro_max/visual_motifs",
    ]
    assert "score" in first


def test_search_ux_guidelines_returns_platform_guidance() -> None:
    results = search_ux_guidelines("smooth scroll anchor navigation web")

    assert results
    first = results[0]
    assert first["dataset_id"] == "ux_guidelines"
    assert first["issue"] == "Smooth Scroll"
    assert first["platform"] == "Web"
    assert first["severity"] == "High"


def test_search_landing_patterns_returns_cta_and_section_flow() -> None:
    results = search_landing_patterns("hero cta sticky conversion")

    assert results
    first = results[0]
    assert first["dataset_id"] == "landing_patterns"
    assert "primary_cta_placement" in first
    assert "section_order" in first


def test_search_typography_pairings_returns_font_notes() -> None:
    results = search_typography_pairings("premium editorial luxury")

    assert results
    first = results[0]
    assert first["dataset_id"] == "typography_pairings"
    assert "heading_font" in first
    assert "body_font" in first
    assert "notes" in first


def test_search_color_systems_returns_palette_fields() -> None:
    results = search_color_systems("saas trust orange cta")

    assert results
    first = results[0]
    assert first["dataset_id"] == "color_systems"
    assert first["accent"]
    assert first["background"]
    assert first["foreground"]


def test_search_chart_patterns_spans_ui_ux_and_vega_lite() -> None:
    results = search_chart_patterns("time series growth line")

    assert results
    dataset_ids = {result["dataset_id"] for result in results}
    assert dataset_ids <= {"chart_usage_patterns", "chart_patterns"}
    assert any(result.get("best_chart_type") == "Line Chart" for result in results)


def test_search_report_layouts_returns_table_figure_conventions() -> None:
    results = search_report_layouts("figure width pdf report")

    assert results
    assert any(
        result["dataset_id"] == "table_figure_conventions"
        and result.get("option") == "fig-width"
        for result in results
    )


def test_search_quarto_layouts_returns_callout_pattern() -> None:
    results = search_quarto_layouts("collapsible dark mode callout")

    assert results
    first = results[0]
    assert first["dataset_id"] == "callout_patterns"
    assert first["renderer_tier"] == "bootstrap-html"
    assert "collapsible" in first["features"]
