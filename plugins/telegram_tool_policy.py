"""Central Telegram front-door tool-surface policy for project-local tools.

This module is the single source of truth for how Vizier's project-local
Hermes tools should appear across Telegram modes:

- ``assistant-safe``: visible in assistant, work, and operator modes
- ``work-only``: visible only in ``vizier_work``
- ``operator-only``: visible only in ``operator``
- ``shared``: visible in both ``vizier_work`` and ``operator``

Non-Telegram sessions are unaffected because the underlying gating helper
passes through when the current platform is not Telegram.
"""
from __future__ import annotations

from typing import Final

from plugins.telegram_mode_state import telegram_mode_allows

ASSISTANT_SAFE: Final = "assistant-safe"
WORK_ONLY: Final = "work-only"
OPERATOR_ONLY: Final = "operator-only"
SHARED: Final = "shared"

TOOLS_BY_CLASSIFICATION: Final[dict[str, frozenset[str]]] = {
    ASSISTANT_SAFE: frozenset(),
    WORK_ONLY: frozenset(
        {
            "generate_poster",
            "search_palettes",
            "search_fonts",
            "search_ui_styles",
            "search_ux_guidelines",
            "search_chart_patterns",
            "search_report_layouts",
            "search_quarto_layouts",
        }
    ),
    OPERATOR_ONLY: frozenset({"query_costs", "query_logs"}),
    SHARED: frozenset(
        {
            "run_pipeline",
            "switch_toolset",
            "decompose_task",
            "merge_results",
        }
    ),
}

ALLOWED_MODES_BY_CLASSIFICATION: Final[dict[str, tuple[str, ...]]] = {
    ASSISTANT_SAFE: ("assistant", "vizier_work", "operator"),
    WORK_ONLY: ("vizier_work",),
    OPERATOR_ONLY: ("operator",),
    SHARED: ("vizier_work", "operator"),
}

TELEGRAM_TOOL_CLASSIFICATIONS: Final[dict[str, str]] = {
    tool_name: classification
    for classification, tool_names in TOOLS_BY_CLASSIFICATION.items()
    for tool_name in tool_names
}

PROJECT_LOCAL_TELEGRAM_TOOLS: Final[frozenset[str]] = frozenset(
    TELEGRAM_TOOL_CLASSIFICATIONS
)


def telegram_tool_classification(tool_name: str) -> str:
    """Return the explicit Telegram audience classification for a tool."""
    try:
        return TELEGRAM_TOOL_CLASSIFICATIONS[tool_name]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise KeyError(
            f"Tool '{tool_name}' is missing from the Telegram tool policy."
        ) from exc


def telegram_tool_allowed_modes(tool_name: str) -> tuple[str, ...]:
    """Return the Telegram modes allowed to see the tool."""
    classification = telegram_tool_classification(tool_name)
    return ALLOWED_MODES_BY_CLASSIFICATION[classification]


def telegram_tool_allows(tool_name: str) -> bool:
    """Return whether the current Telegram turn should see the tool."""
    return telegram_mode_allows(*telegram_tool_allowed_modes(tool_name))
