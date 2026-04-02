"""Tests for Telegram mode routing."""
from __future__ import annotations

from plugins.telegram_mode_router import (
    build_telegram_mode_context,
    classify_telegram_mode,
)


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
        user_message="Make a proposal and poster for our client launch next week.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "vizier_work"
    assert decision.source == "keyword_inference"


def test_operator_inference_for_repo_request() -> None:
    decision = classify_telegram_mode(
        user_message="Fix the failing pytest in the poster pipeline and commit it.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "operator"
    assert decision.source == "keyword_inference"


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


def test_context_mentions_mode_and_overrides() -> None:
    context = build_telegram_mode_context(
        user_message="Remind me to reply to Ahmad tomorrow morning.",
        conversation_history=[],
        platform="telegram",
    )

    assert "Current mode: assistant" in context
    assert "/assist, /work, or /ops" in context
