"""Tests for normalized dataset presence and shape."""
from __future__ import annotations

from references.inventory import load_normalized_dataset


def test_ui_ux_styles_dataset_shape() -> None:
    payload = load_normalized_dataset("ui_ux_pro_max", "ui_styles")
    assert payload["record_count"] == len(payload["items"])
    first = payload["items"][0]
    assert {"id", "name", "keywords", "best_for", "avoid_for"} <= set(first)


def test_vega_chart_pattern_dataset_shape() -> None:
    payload = load_normalized_dataset("vega_lite", "chart_patterns")
    assert payload["record_count"] == len(payload["items"])
    first = payload["items"][0]
    assert {"marks", "channels", "composition", "analytic_goal"} <= set(first)


def test_quarto_publishing_dataset_shape() -> None:
    payload = load_normalized_dataset("quarto", "publishing_patterns")
    assert payload["record_count"] == len(payload["items"])
    first = payload["items"][0]
    assert {"project_type", "primary_outputs", "layout_notes"} <= set(first)
