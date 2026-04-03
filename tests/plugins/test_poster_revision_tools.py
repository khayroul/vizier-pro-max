"""Tests for the poster revision Hermes tool surface."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _tool_map(ctx: MagicMock) -> dict[str, dict[str, object]]:
    return {call.kwargs["name"]: call.kwargs for call in ctx.register_tool.call_args_list}


def test_on_agent_ready_registers_revision_tools() -> None:
    """Poster tool plugin should expose the new structured revision helpers."""
    from plugins.poster_tool import register

    ctx = MagicMock()
    register(ctx)

    hook = ctx.register_hook.call_args[0][1]
    agent = SimpleNamespace(_custom_agent_tools={})
    hook(agent)

    assert {
        "generate_poster",
        "prepare_poster_revision",
        "revise_poster_structured",
        "check_poster_revision",
        "resolve_brand_asset",
        "summarize_poster_revision",
        "revise_poster",
    } <= set(agent._custom_agent_tools)


@patch("plugins.poster_tool.record_feedback_note")
@patch("pipelines.poster_revision.prepare_poster_revision")
def test_prepare_revision_handler_returns_compact_summary(
    mock_prepare: MagicMock,
    mock_record_feedback: MagicMock,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Prepare handler should forward structured inputs and preserve Telegram-friendly summary text."""
    from plugins.poster_tool import _handle_prepare_poster_revision
    from plugins.telegram_poster_session import record_reference_image

    monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-session")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    record_reference_image("/tmp/reference-sample.png", source="telegram_photo")
    mock_prepare.return_value = {
        "status": "ready",
        "telegram_summary": "I’m revising 3 things: stronger brand visibility, one main headline only, cleaner hierarchy.",
        "revision_plan": {
            "feedback": "Make the logo bigger.",
            "change_goals": [{"key": "brand_visibility"}],
        },
    }

    payload = json.loads(
        _handle_prepare_poster_revision(
            {
                "feedback": "Make the logo bigger.",
                "latest_poster_path": "/tmp/poster.png",
            },
            None,
        )
    )

    assert payload["status"] == "ready"
    assert payload["telegram_summary"].startswith("I’m revising")
    assert mock_prepare.call_args.kwargs["reference_image_path"] == "/tmp/reference-sample.png"
    assert mock_record_feedback.called


@patch("plugins.poster_tool.record_poster_result")
@patch("plugins.poster_tool.record_feedback_note")
@patch("pipelines.poster_revision.revise_poster_structured")
def test_revise_structured_handler_records_result(
    mock_revise: MagicMock,
    mock_record_feedback: MagicMock,
    mock_record_result: MagicMock,
) -> None:
    """Structured revise handler should return stable JSON and track the revised artifact."""
    from plugins.poster_tool import _handle_revise_poster_structured

    mock_revise.return_value = {
        "status": "revised",
        "poster_path": "/tmp/revised-poster.png",
        "revision_plan": {
            "feedback": "Clean it up.",
            "change_goals": [{"key": "cleaner_hierarchy"}],
        },
        "applied_changes": [{"key": "cleaner_hierarchy", "status": "applied"}],
        "telegram_summary": "I revised the poster toward cleaner hierarchy.",
    }

    payload = json.loads(
        _handle_revise_poster_structured(
            {
                "feedback": "Clean it up.",
                "prepared_revision": {"status": "ready"},
            },
            None,
        )
    )

    assert payload["status"] == "revised"
    assert payload["applied_changes"][0]["key"] == "cleaner_hierarchy"
    assert mock_record_feedback.called
    assert mock_record_result.call_args.kwargs["tool_name"] == "revise_poster_structured"


@patch("pipelines.poster_revision.check_poster_revision")
def test_check_revision_handler_returns_safe_summary(
    mock_check: MagicMock,
) -> None:
    """Check handler should preserve the stable per-goal status contract."""
    from plugins.poster_tool import _handle_check_poster_revision

    mock_check.return_value = {
        "status": "checked",
        "overall_status": "needs_visual_review",
        "goal_statuses": [{"key": "brand_visibility", "status": "supported"}],
        "telegram_summary": "I increased the logo emphasis. The official logo still depends on a provided local asset.",
    }

    payload = json.loads(
        _handle_check_poster_revision(
            {
                "revised_poster_result": {"poster_path": "/tmp/revised-poster.png"},
            },
            None,
        )
    )

    assert payload["status"] == "checked"
    assert payload["goal_statuses"][0]["key"] == "brand_visibility"
    assert "official logo" in payload["telegram_summary"].lower()


def test_resolve_brand_asset_handler_is_truthful_with_client_text_mark() -> None:
    """Client config should resolve to text_mark_only when no local asset path exists."""
    from plugins.poster_tool import _handle_resolve_brand_asset

    payload = json.loads(
        _handle_resolve_brand_asset(
            {
                "client_id": "dmb",
            },
            None,
        )
    )

    assert payload["status"] == "text_mark_only"
    assert payload["asset_path"] == ""
    assert "logo asset" in " ".join(payload["notes"]).lower()


def test_summarize_revision_handler_prefers_check_payload() -> None:
    """Summary helper should let the front door stay thin."""
    from plugins.poster_tool import _handle_summarize_poster_revision

    payload = json.loads(
        _handle_summarize_poster_revision(
            {
                "stage": "auto",
                "check_result": {
                    "telegram_summary": "I increased the logo emphasis and kept one main headline.",
                    "claim_level": "soft",
                },
            },
            None,
        )
    )

    assert payload["status"] == "summarized"
    assert payload["stage"] == "check"
    assert "one main headline" in payload["telegram_summary"]
