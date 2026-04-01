"""Tests for send_telegram delivery wrapper."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSendTelegram:
    def test_send_text_message(self) -> None:
        from scripts.delivery.send_telegram import run

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"}), \
             patch("scripts.delivery.send_telegram._send_message") as mock:
            mock.return_value = {"message_id": 123, "status": "sent"}
            result = run(
                chat_id="12345",
                text="Hello from Vizier",
            )
        assert result["status"] == "sent"
        assert result["message_id"] == 123

    def test_send_file(self, tmp_path) -> None:
        from scripts.delivery.send_telegram import run

        fake_file = tmp_path / "report.pdf"
        fake_file.write_bytes(b"%PDF-fake")

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"}), \
             patch("scripts.delivery.send_telegram._send_document") as mock:
            mock.return_value = {"message_id": 456, "status": "sent"}
            result = run(
                chat_id="12345",
                file_path=str(fake_file),
            )
        assert result["status"] == "sent"

    def test_missing_chat_id_raises(self) -> None:
        from scripts.delivery.send_telegram import run

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"}):
            with pytest.raises(ValueError, match="chat_id"):
                run(text="hello")

    def test_missing_token_raises(self) -> None:
        from scripts.delivery.send_telegram import run

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                run(chat_id="12345", text="hello")
