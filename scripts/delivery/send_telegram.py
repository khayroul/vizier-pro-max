"""Telegram delivery via python-telegram-bot."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog

from adapter.env_loader import ensure_env

logger = structlog.get_logger(__name__)

ensure_env()


async def _async_send_message(chat_id: str, text: str, token: str) -> dict[str, Any]:
    from telegram import Bot

    bot = Bot(token=token)
    msg = await bot.send_message(chat_id=chat_id, text=text)
    return {"message_id": msg.message_id, "status": "sent"}


async def _async_send_document(
    chat_id: str, file_path: str, caption: str | None, token: str,
) -> dict[str, Any]:
    from telegram import Bot

    bot = Bot(token=token)
    with open(file_path, "rb") as f:
        msg = await bot.send_document(chat_id=chat_id, document=f, caption=caption)
    return {"message_id": msg.message_id, "status": "sent"}


def _send_message(chat_id: str, text: str, token: str) -> dict[str, Any]:
    return asyncio.run(_async_send_message(chat_id, text, token))


def _send_document(
    chat_id: str, file_path: str, caption: str | None, token: str,
) -> dict[str, Any]:
    return asyncio.run(_async_send_document(chat_id, file_path, caption, token))


def run(
    *,
    chat_id: str | None = None,
    text: str | None = None,
    file_path: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Send a message or file via Telegram."""
    if not chat_id:
        msg = "chat_id is required"
        raise ValueError(msg)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        msg = "TELEGRAM_BOT_TOKEN environment variable is required"
        raise RuntimeError(msg)

    if file_path:
        return _send_document(chat_id, file_path, caption, token)
    if text:
        return _send_message(chat_id, text, token)

    msg = "Must provide text or file_path"
    raise ValueError(msg)
