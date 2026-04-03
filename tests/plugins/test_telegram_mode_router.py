"""Tests for Telegram mode routing."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugins.telegram_mode_router import (
    build_telegram_mode_context,
    classify_telegram_mode,
    prime_telegram_mode,
)
from plugins.telegram_poster_session import record_poster_result
from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode, telegram_mode_allows


@pytest.fixture(autouse=True)
def _clear_mode_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIZIER_TELEGRAM_FRONT_DOOR", raising=False)
    monkeypatch.delenv("MESSAGING_CWD", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_SESSION_KEY", raising=False)
    monkeypatch.delenv("HERMES_SESSION_PLATFORM", raising=False)
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
    assert "first call switch_toolset" in context


def test_poster_critique_can_remain_assistant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-poster")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")

    record_poster_result(
        tool_name="generate_poster",
        tool_args={"brief": "PETRONAS Raya poster"},
        result_payload={"poster_path": "/tmp/poster.png"},
    )
    prime_telegram_mode(
        user_message="Give feedback on this poster only.",
        conversation_history=[],
        platform="telegram",
    )

    decision = classify_telegram_mode(
        user_message="Give feedback on this poster only.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "assistant"
    assert decision.source == "poster_critique"


def test_poster_feedback_with_prior_poster_routes_to_vizier_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-poster")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")

    record_poster_result(
        tool_name="generate_poster",
        tool_args={"brief": "PETRONAS Raya poster"},
        result_payload={"poster_path": "/tmp/poster.png"},
    )
    prime_telegram_mode(
        user_message="Make the logo more visible and clean up the layout.",
        conversation_history=[],
        platform="telegram",
    )

    decision = classify_telegram_mode(
        user_message="Make the logo more visible and clean up the layout.",
        conversation_history=[],
        platform="telegram",
    )

    assert decision.mode == "vizier_work"
    assert decision.source == "poster_revision"


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
