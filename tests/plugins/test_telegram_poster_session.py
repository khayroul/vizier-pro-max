"""Tests for Telegram poster session intake and state isolation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plugins.telegram_poster_session import (
    build_telegram_poster_context,
    clear_current_poster_turn_signals,
    load_poster_session_state,
    observe_telegram_poster_turn,
    record_poster_result,
    record_reference_image,
    register,
)


@pytest.fixture(autouse=True)
def _session_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
    monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-session-a")
    clear_current_poster_turn_signals()


def test_register_adds_expected_hooks() -> None:
    """Project plugin registration should expose the poster session lifecycle hooks."""
    ctx = MagicMock()
    register(ctx)

    hook_names = [call.args[0] for call in ctx.register_hook.call_args_list]
    assert hook_names.count("pre_tool_resolution") == 1
    assert hook_names.count("pre_llm_call") == 1
    assert hook_names.count("post_tool_call") == 1


def test_photo_turn_updates_active_reference_image_path() -> None:
    """Telegram photo intake becomes the active poster reference for the session."""
    signals = observe_telegram_poster_turn(
        user_message=(
            "[The user sent an image~ Here's what I can see: festive poster]\n"
            "[If you need a closer look, use vision_analyze with "
            "image_url: /tmp/photo-reference.png ~]"
        ),
        platform="telegram",
    )

    state = load_poster_session_state()

    assert signals is not None
    assert signals.reference_image_updated is True
    assert signals.reference_image_path == "/tmp/photo-reference.png"
    assert state.latest_reference_image_path == "/tmp/photo-reference.png"
    assert state.latest_reference_source == "telegram_photo"


def test_image_document_turn_updates_active_reference_image_path() -> None:
    """Telegram PNG/JPG/JPEG image documents should become active poster references."""
    signals = observe_telegram_poster_turn(
        user_message=(
            "[The user sent a document: 'sample-poster.png'. "
            "The file is saved at: /tmp/doc_123_sample-poster.png. "
            "Ask the user what they'd like you to do with it.]"
        ),
        platform="telegram",
    )

    state = load_poster_session_state()

    assert signals is not None
    assert signals.reference_image_updated is True
    assert signals.reference_image_path == "/tmp/doc_123_sample-poster.png"
    assert signals.reference_source == "telegram_image_document"
    assert state.latest_reference_image_path == "/tmp/doc_123_sample-poster.png"


def test_unsupported_poster_reference_prompts_for_supported_formats() -> None:
    """Poster-intent unsupported files should be rejected with clear PNG/JPG/JPEG guidance."""
    record_poster_result(
        tool_name="generate_poster",
        tool_args={"brief": "PETRONAS Raya poster"},
        result_payload={"poster_path": "/tmp/original-poster.png"},
    )

    signals = observe_telegram_poster_turn(
        user_message=(
            "[The user sent a document: 'sample.pdf'. "
            "The file is saved at: /tmp/doc_123_sample.pdf. "
            "Ask the user what they'd like you to do with it.]\n\n"
            "Use this sample to revise my poster."
        ),
        platform="telegram",
    )
    context = build_telegram_poster_context(platform="telegram")

    assert signals is not None
    assert signals.unsupported_reference_extension == ".pdf"
    assert "PNG, JPG, or JPEG" in context


def test_poster_session_state_does_not_bleed_across_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poster reference and artifact state must stay isolated per Telegram session."""
    record_reference_image("/tmp/session-a-reference.png", source="telegram_photo")

    monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-session-b")
    state = load_poster_session_state()

    assert state.latest_reference_image_path == ""
