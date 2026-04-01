"""WhatsApp Business API delivery via httpx."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v18.0"


def run(
    *,
    to_phone: str,
    text: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Send a message via WhatsApp Business API."""
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")

    if not token:
        msg = "WHATSAPP_TOKEN environment variable required"
        raise RuntimeError(msg)
    if not phone_id:
        msg = "WHATSAPP_PHONE_ID environment variable required"
        raise RuntimeError(msg)

    url = f"{WHATSAPP_API_URL}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if text:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
    else:
        msg = "text is required (file delivery not yet implemented)"
        raise ValueError(msg)

    response = httpx.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()

    message_id = data.get("messages", [{}])[0].get("id", "")
    logger.info("WhatsApp message sent: %s", message_id)
    return {"status": "sent", "message_id": message_id}
