"""Tests for Telegram mode routing."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)

from plugins.telegram_mode_router import (
    build_telegram_mode_context,
    classify_telegram_mode,
    prime_telegram_mode,
)
from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode, telegram_mode_allows


@pytest.fixture(autouse=True)
def _clear_mode_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIZIER_TELEGRAM_FRONT_DOOR", raising=False)
    monkeypatch.delenv("MESSAGING_CWD", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("HERMES_TELEGRAM_POSTER_PATH", raising=False)
    clear_telegram_mode()


def test_explicit_assist_override_wins() -> None:
    decision = classify_telegram_mode(
        user_message="/assist help me plan my day",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "assistant"
    assert decision.source == "explicit_command"


def test_vizier_work_inference_for_deliverable_request() -> None:
    decision = classify_telegram_mode(
        user_message="Make me a poster for our client launch next week.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "vizier_work"
    assert decision.source == "keyword_inference"
    assert decision.workflow_toolset == "vizier-visual"


def test_professional_support_request_stays_in_assistant_mode() -> None:
    decision = classify_telegram_mode(
        user_message="Help me think through a business decision for next quarter.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "assistant"
    assert decision.source == "keyword_inference"


def test_operator_inference_for_repo_request() -> None:
    decision = classify_telegram_mode(
        user_message="Fix the failing pytest in the poster pipeline and commit it.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "operator"
    assert decision.source == "keyword_inference"


def test_poster_feedback_in_active_session_routes_to_vizier_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_TELEGRAM_POSTER_PATH", "/tmp/poster.png")

    decision = classify_telegram_mode(
        user_message="I can't see the logo and the layout still feels empty.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "vizier_work"
    assert decision.source == "poster_session_feedback"
    assert decision.workflow_toolset == "vizier-visual"


def test_sticky_mode_uses_recent_override_when_current_turn_is_ambiguous() -> None:
    decision = classify_telegram_mode(
        user_message="Do the next one too.",
        conversation_history=[
            {"role": "user", "content": "/work"},
            {"role": "assistant", "content": "Ready for Vizier work mode."},
        ],
        platform="telegram",
    )

    assert decision.mode == "vizier_work"
    assert decision.source == "sticky_override"


def test_context_is_empty_off_telegram() -> None:
    context = build_telegram_mode_context(
        user_message="Make a poster",
        conversation_history=[],
        platform="cli",
    )

    assert context == ""


def test_non_telegram_platform_keeps_tool_gating_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")

    context = build_telegram_mode_context(
        user_message="Make a poster",
        conversation_history=[],
        platform="cli",
    )

    assert context == ""
    assert telegram_mode_allows("vizier_work") is True
    assert telegram_mode_allows("operator") is True


def test_context_is_empty_when_platform_is_missing() -> None:
    context = build_telegram_mode_context(
        user_message="Make a poster",
        conversation_history=[],
        platform="",
    )

    assert context == ""


def test_context_mentions_mode_and_overrides() -> None:
    context = build_telegram_mode_context(
        user_message="Remind me to reply to Ahmad tomorrow morning.",
        conversation_history=[],
        platform="telegram",
    )

    assert "Current mode: assistant" in context
    assert "/assist, /work, or /ops" in context


def test_old_sticky_override_expires_after_short_window() -> None:
    decision = classify_telegram_mode(
        user_message="Do the next one too.",
        conversation_history=[
            {"role": "user", "content": "/work"},
            {"role": "assistant", "content": "Ready for Vizier work mode."},
            {"role": "user", "content": "Thanks"},
            {"role": "user", "content": "What do you think?"},
            {"role": "user", "content": "Maybe later"},
        ],
        platform="telegram",
    )

    assert decision.mode == "assistant"
    assert decision.source == "default"


def test_work_mode_context_mentions_switch_toolset() -> None:
    context = build_telegram_mode_context(
        user_message="/work Make a poster for our launch",
        conversation_history=[],
        platform="telegram",
    )

    assert "Current mode: vizier_work" in context
    assert "workflow surface should already be active" in context
    assert "vizier-visual" in context


def test_prime_telegram_mode_auto_activates_matching_workflow_toolset() -> None:
    agent = type("Agent", (), {"enabled_toolsets": ["vizier-core", "code_execution"]})()

    decision = prime_telegram_mode(
        user_message="Make me a poster for our launch",
        conversation_history=[],
        platform="telegram",
        agent=agent,
    )

    assert decision is not None
    assert decision.workflow_toolset == "vizier-visual"
    assert agent.enabled_toolsets == [
        "vizier-core",
        "code_execution",
        "vizier-visual",
    ]


def test_front_door_defaults_to_assistant_gating_until_mode_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")

    assert telegram_mode_allows("assistant") is True
    assert telegram_mode_allows("vizier_work") is False


def test_work_mode_gating_opens_vizier_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    set_telegram_mode(platform="telegram", mode="vizier_work")

    assert telegram_mode_allows("vizier_work") is True
    assert telegram_mode_allows("operator") is False
