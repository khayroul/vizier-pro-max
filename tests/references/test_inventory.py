"""Tests for normalized reference inventory shape."""
from __future__ import annotations

from references.inventory import build_reference_inventory


def test_inventory_contains_expected_dataset_ids() -> None:
    inventory = build_reference_inventory()
    dataset_ids = {
        item.manifest.family: {dataset.dataset_id for dataset in item.datasets}
        for item in inventory
    }
    assert dataset_ids["ui_ux_pro_max"] >= {
        "ui_styles",
        "visual_motifs",
        "ux_guidelines",
        "landing_patterns",
        "chart_usage_patterns",
    }
    assert dataset_ids["vega_lite"] == {"chart_grammar", "chart_patterns"}
    assert dataset_ids["quarto"] >= {
        "document_layout_options",
        "table_figure_conventions",
        "callout_patterns",
        "publishing_patterns",
        "longform_structure_patterns",
    }


def test_inventory_record_counts_are_positive() -> None:
    inventory = build_reference_inventory()
    assert inventory
    for family in inventory:
        assert family.datasets
        for dataset in family.datasets:
            assert dataset.record_count > 0
            assert dataset.description
