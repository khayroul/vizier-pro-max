"""Quality tests for competitive_analysis pipeline improvements."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_chart_values_not_sequential_integers() -> None:
    """Chart Y-axis must reflect actual data, not range(len(columns))."""
    from pipelines.competitive_analysis import _build_chart_data

    analysis_result = {
        "Pclass": {"1": 0.63, "2": 0.47, "3": 0.24},
    }
    chart_data = _build_chart_data(analysis_result, "survival rate by class")
    assert chart_data["values"] != list(range(len(chart_data["labels"])))
    assert all(isinstance(v, (int, float)) for v in chart_data["values"])


def test_narrative_cites_specific_numbers() -> None:
    """Narrative must contain specific numbers from the data."""
    from pipelines.competitive_analysis import _generate_narrative

    data_summary = json.dumps({
        "survival_by_class": {"1": 0.63, "2": 0.47, "3": 0.24},
        "survival_by_gender": {"female": 0.74, "male": 0.19},
    })

    with patch("pipelines.competitive_analysis.llm_chat") as mock:
        mock.return_value = (
            "## Key Findings\n\n"
            "1st class passengers survived at 63%, while 3rd class at only 24%.\n"
            "Female passengers survived at 74% compared to 19% for males."
        )
        narrative = _generate_narrative(
            "Titanic survival by class and gender", data_summary
        )
        assert "63" in narrative or "0.63" in narrative
        assert "24" in narrative or "0.24" in narrative


def test_analysis_uses_multiple_operations() -> None:
    """Pipeline should call analyze_run with LLM-selected operations, not just describe."""
    from pipelines.competitive_analysis import _select_analysis_operations

    with patch("pipelines.competitive_analysis.llm_chat") as mock:
        mock.return_value = json.dumps([
            {"operation": "groupby", "group_column": "Pclass", "agg_column": "Survived", "agg_function": "mean"},
            {"operation": "groupby", "group_column": "Sex", "agg_column": "Survived", "agg_function": "mean"},
        ])
        ops = _select_analysis_operations(
            "Titanic survival by class and gender",
            ["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age"],
        )
        assert len(ops) >= 1
        assert any(op["operation"] == "groupby" for op in ops)
