"""Tests for the centralized Telegram tool-surface policy."""
from __future__ import annotations

from plugins.telegram_tool_policy import (
    ALLOWED_MODES_BY_CLASSIFICATION,
    ASSISTANT_SAFE,
    OPERATOR_ONLY,
    PROJECT_LOCAL_TELEGRAM_TOOLS,
    SHARED,
    TELEGRAM_TOOL_CLASSIFICATIONS,
    TOOLS_BY_CLASSIFICATION,
    WORK_ONLY,
    telegram_tool_allowed_modes,
    telegram_tool_classification,
)


def test_policy_classifies_each_project_local_tool_once() -> None:
    expected = {
        "generate_poster",
        "revise_poster",
        "search_palettes",
        "search_fonts",
        "search_ui_styles",
        "search_ux_guidelines",
        "search_chart_patterns",
        "search_report_layouts",
        "search_quarto_layouts",
        "query_costs",
        "query_logs",
        "run_pipeline",
        "switch_toolset",
        "decompose_task",
        "merge_results",
    }

    assert PROJECT_LOCAL_TELEGRAM_TOOLS == expected
    assert set(TELEGRAM_TOOL_CLASSIFICATIONS) == expected


def test_policy_groups_match_expected_surface() -> None:
    assert TOOLS_BY_CLASSIFICATION[ASSISTANT_SAFE] == frozenset()
    assert TOOLS_BY_CLASSIFICATION[WORK_ONLY] == frozenset(
        {
            "generate_poster",
            "revise_poster",
            "search_palettes",
            "search_fonts",
            "search_ui_styles",
            "search_ux_guidelines",
            "search_chart_patterns",
            "search_report_layouts",
            "search_quarto_layouts",
        }
    )
    assert TOOLS_BY_CLASSIFICATION[OPERATOR_ONLY] == frozenset(
        {"query_costs", "query_logs"}
    )
    assert TOOLS_BY_CLASSIFICATION[SHARED] == frozenset(
        {"run_pipeline", "switch_toolset", "decompose_task", "merge_results"}
    )


def test_policy_groups_are_disjoint() -> None:
    seen: set[str] = set()
    for tool_names in TOOLS_BY_CLASSIFICATION.values():
        assert seen.isdisjoint(tool_names)
        seen.update(tool_names)


def test_allowed_modes_follow_classification() -> None:
    assert ALLOWED_MODES_BY_CLASSIFICATION[ASSISTANT_SAFE] == (
        "assistant",
        "vizier_work",
        "operator",
    )
    assert telegram_tool_classification("generate_poster") == WORK_ONLY
    assert telegram_tool_allowed_modes("generate_poster") == ("vizier_work",)
    assert telegram_tool_classification("revise_poster") == WORK_ONLY
    assert telegram_tool_allowed_modes("revise_poster") == ("vizier_work",)
    assert telegram_tool_classification("query_logs") == OPERATOR_ONLY
    assert telegram_tool_allowed_modes("query_logs") == ("operator",)
    assert telegram_tool_classification("run_pipeline") == SHARED
    assert telegram_tool_allowed_modes("run_pipeline") == (
        "vizier_work",
        "operator",
    )
