"""Tests for send_whatsapp delivery wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSendWhatsapp:
    def test_send_text_message(self) -> None:
        from scripts.delivery.send_whatsapp import run

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("os.environ", {"WHATSAPP_TOKEN": "test", "WHATSAPP_PHONE_ID": "123"}):
            result = run(
                to_phone="+60123456789",
                text="Hello from Vizier",
            )
        assert result["status"] == "sent"

    def test_missing_env_vars_raises(self) -> None:
        from scripts.delivery.send_whatsapp import run

        with patch.dict("os.environ", {}, clear=True), \
             pytest.raises(RuntimeError, match="WHATSAPP_TOKEN"):
            run(to_phone="+60123456789", text="test")

    def test_api_error(self) -> None:
        from scripts.delivery.send_whatsapp import run

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("os.environ", {"WHATSAPP_TOKEN": "bad", "WHATSAPP_PHONE_ID": "123"}), \
             pytest.raises(Exception, match="401"):
            run(to_phone="+60123456789", text="test")
