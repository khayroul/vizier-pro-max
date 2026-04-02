"""Telegram entrypoint for the marketing-plan pipeline."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapter.env_loader import ensure_env
from pipelines.longform.spine import slugify
from scripts.delivery.send_telegram import run as send_telegram_run
from tools.run_pipeline import run_pipeline

ensure_env()


def _derive_title(text: str) -> str:
    """Derive a short title from a Telegram brief."""
    words = [part.strip(" ,.:;!?") for part in text.split() if part.strip(" ,.:;!?")]
    return " ".join(words[:6]).title() or "Marketing Plan"


def _build_pipeline_args(
    *,
    brief: str,
    client_id: str = "",
    output_root: str = "output/telegram-marketing",
) -> dict[str, Any]:
    """Build deterministic pipeline args for Telegram-triggered runs."""
    title = _derive_title(brief)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(output_root) / f"{slugify(title)}-{timestamp}"
    args: dict[str, Any] = {
        "brief": brief.strip(),
        "title": title,
        "output_dir": str(run_dir),
        "package_mode": "document_bundle",
        "generate_posters": True,
        "export_epub": False,
    }
    if client_id:
        args["client_id"] = client_id
    return args


def generate_marketing_package(
    *,
    brief: str,
    client_id: str = "",
    output_root: str = "output/telegram-marketing",
) -> dict[str, Any]:
    """Run the marketing-plan pipeline from a Telegram brief."""
    payload = json.loads(
        run_pipeline(
            {
                "name": "marketing_plan_generate",
                "args": _build_pipeline_args(
                    brief=brief,
                    client_id=client_id,
                    output_root=output_root,
                ),
            }
        )
    )
    if "error" in payload:
        msg = str(payload["error"])
        raise RuntimeError(msg)
    return payload


def collect_client_files(result: dict[str, Any]) -> list[str]:
    """Collect client-facing files from a marketing package result."""
    files: list[str] = []
    for document in result.get("documents", []):
        pdf_path = str(document.get("pdf_path", "")).strip()
        if pdf_path:
            files.append(pdf_path)
    for poster_path in (
        result.get("operational_assets", {}).get("client_poster_paths", [])
    ):
        poster_path = str(poster_path).strip()
        if poster_path:
            files.append(poster_path)
    deduped: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            deduped.append(file_path)
    return deduped


def _build_summary_text(result: dict[str, Any]) -> str:
    """Build a short Telegram delivery summary."""
    doc_count = int(result.get("document_count", 0))
    poster_count = int(result.get("poster_count", 0))
    title = str(result.get("title", "Marketing package")).strip()
    return (
        f"{title} is ready.\n"
        f"Documents: {doc_count}\n"
        f"Client posters: {poster_count}"
    )


def send_marketing_package(
    *,
    chat_id: str,
    result: dict[str, Any],
) -> None:
    """Send client-facing outputs for a generated marketing package."""
    send_telegram_run(chat_id=chat_id, text=_build_summary_text(result))
    for file_path in collect_client_files(result):
        send_telegram_run(chat_id=chat_id, file_path=file_path)


def handle_marketing_brief(
    *,
    chat_id: str,
    brief: str,
    client_id: str = "",
    output_root: str = "output/telegram-marketing",
) -> dict[str, Any]:
    """Generate and deliver a marketing package for one Telegram chat."""
    result = generate_marketing_package(
        brief=brief,
        client_id=client_id,
        output_root=output_root,
    )
    send_marketing_package(chat_id=chat_id, result=result)
    return result


async def _start(update: Any, context: Any) -> None:
    """Send bot welcome text."""
    if update.message is None:
        return
    await update.message.reply_text(
        "Send a marketing brief or use /marketing <brief> and I will return a strategy plan, creative pack, and client-ready posters."
    )


async def _marketing(update: Any, context: Any) -> None:
    """Handle /marketing command."""
    if update.message is None:
        return
    brief = " ".join(context.args).strip() if getattr(context, "args", None) else ""
    if not brief:
        await update.message.reply_text("Send /marketing followed by a brief.")
        return
    await update.message.reply_text("Working on your marketing package now.")
    client_id = os.environ.get("VIZIER_TELEGRAM_CLIENT_ID", "").strip()
    try:
        await asyncio.to_thread(
            handle_marketing_brief,
            chat_id=str(update.effective_chat.id),
            brief=brief,
            client_id=client_id,
            output_root=str(context.application.bot_data.get("output_root", "output/telegram-marketing")),
        )
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Marketing package failed: {exc}")


async def _text_message(update: Any, context: Any) -> None:
    """Treat any free-text message as a marketing brief."""
    if update.message is None or not update.message.text:
        return
    await update.message.reply_text("Working on your marketing package now.")
    client_id = os.environ.get("VIZIER_TELEGRAM_CLIENT_ID", "").strip()
    try:
        await asyncio.to_thread(
            handle_marketing_brief,
            chat_id=str(update.effective_chat.id),
            brief=update.message.text,
            client_id=client_id,
            output_root=str(context.application.bot_data.get("output_root", "output/telegram-marketing")),
        )
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Marketing package failed: {exc}")


def run(
    *,
    output_root: str = "output/telegram-marketing",
) -> None:
    """Run a polling Telegram bot for marketing-package generation."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        msg = "TELEGRAM_BOT_TOKEN environment variable is required"
        raise RuntimeError(msg)

    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

    app = ApplicationBuilder().token(token).build()
    app.bot_data["output_root"] = output_root
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _start))
    app.add_handler(CommandHandler("marketing", _marketing))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text_message))
    app.run_polling()


if __name__ == "__main__":
    run()
