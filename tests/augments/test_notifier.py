"""Tests for augments.selfbuild.notifier."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from augments.selfbuild.notifier import NotificationResult, notify_human
from augments.selfbuild.tier_classifier import TierDecision


@pytest.fixture()
def tier_2_decision() -> TierDecision:
    """Sample Tier 2 decision for notification tests."""
    return TierDecision(
        tier=2,
        reasons=["new atomic tool", "has network side effects"],
        artifact_paths=[Path("/tmp/tools/my_tool.py")],
    )


class TestNotificationResult:
    """NotificationResult is a frozen dataclass."""

    def test_frozen(self) -> None:
        result = NotificationResult(sent=True, message_id=123, error=None)
        with pytest.raises(AttributeError):
            result.sent = False  # type: ignore[misc]


class TestMessageFormatting:
    """Message includes artifact paths and reasons."""

    def test_message_contains_paths_and_reasons(
        self, tier_2_decision: TierDecision
    ) -> None:
        with patch(
            "augments.selfbuild.notifier._send_telegram",
            return_value={"message_id": 42, "status": "sent"},
        ) as mock_send:
            notify_human(
                artifact_paths=tier_2_decision.artifact_paths,
                tier_decision=tier_2_decision,
                chat_id="12345",
            )
            call_text = mock_send.call_args[1]["text"]
            assert "my_tool.py" in call_text
            assert "new atomic tool" in call_text


class TestTelegramApiCall:
    """Telegram send_telegram.run is called correctly."""

    def test_sends_via_telegram(self, tier_2_decision: TierDecision) -> None:
        with patch(
            "augments.selfbuild.notifier._send_telegram",
            return_value={"message_id": 99, "status": "sent"},
        ) as mock_send:
            result = notify_human(
                artifact_paths=tier_2_decision.artifact_paths,
                tier_decision=tier_2_decision,
                chat_id="12345",
            )
            mock_send.assert_called_once()
            assert result.sent is True
            assert result.message_id == 99


class TestMissingChatId:
    """Missing chat_id raises ValueError."""

    def test_no_chat_id_raises(self, tier_2_decision: TierDecision) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="chat_id"):
                notify_human(
                    artifact_paths=tier_2_decision.artifact_paths,
                    tier_decision=tier_2_decision,
                    chat_id=None,
                )


class TestSendTelegramDynamicImport:
    """_send_telegram delegates to scripts.delivery.send_telegram.run (lines 62-64)."""

    def test_send_telegram_calls_dynamic_import(self) -> None:
        from unittest.mock import MagicMock

        mock_module = MagicMock()
        mock_module.run.return_value = {"message_id": 7, "status": "sent"}

        with patch.dict(
            "sys.modules",
            {"scripts": MagicMock(), "scripts.delivery": MagicMock(), "scripts.delivery.send_telegram": mock_module},
        ):
            from augments.selfbuild.notifier import _send_telegram

            result = _send_telegram(chat_id="999", text="hello")

        mock_module.run.assert_called_once_with(chat_id="999", text="hello")
        assert result == {"message_id": 7, "status": "sent"}


class TestMissingTelegramToken:
    """Missing TELEGRAM_BOT_TOKEN handled gracefully."""

    def test_missing_token_returns_error(
        self, tier_2_decision: TierDecision
    ) -> None:
        with patch.dict("os.environ", {"VIZIER_ADMIN_CHAT_ID": "12345"}, clear=True):
            with patch(
                "augments.selfbuild.notifier._send_telegram",
                side_effect=RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required"),
            ):
                result = notify_human(
                    artifact_paths=tier_2_decision.artifact_paths,
                    tier_decision=tier_2_decision,
                    chat_id="12345",
                )
                assert result.sent is False
                assert result.error is not None
                assert "TELEGRAM_BOT_TOKEN" in result.error
