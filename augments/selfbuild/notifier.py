"""Send Telegram notification for Tier 2 human approval.

Includes: artifact type, file paths, approve/reject prompt.
Uses existing scripts/delivery/send_telegram.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from augments.selfbuild.tier_classifier import TierDecision

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class NotificationResult:
    """Result of a notification attempt."""

    sent: bool
    message_id: int | None
    error: str | None


def _format_message(
    artifact_paths: list[Path],
    tier_decision: TierDecision,
) -> str:
    """Format a human-readable approval request message.

    Args:
        artifact_paths: Paths to the artifacts requiring review.
        tier_decision: The classification decision with reasons.

    Returns:
        Formatted message string.
    """
    paths_str = "\n".join(f"  - {p.name}" for p in artifact_paths)
    reasons_str = "\n".join(f"  - {r}" for r in tier_decision.reasons)
    return (
        f"[Vizier Self-Build] Tier {tier_decision.tier} artifact awaiting review\n\n"
        f"Artifacts:\n{paths_str}\n\n"
        f"Reasons:\n{reasons_str}\n\n"
        f"Reply /approve or /reject to this thread."
    )


def _send_telegram(*, chat_id: str, text: str) -> dict[str, Any]:
    """Delegate to scripts.delivery.send_telegram.run.

    Args:
        chat_id: Telegram chat ID.
        text: Message text.

    Returns:
        Response dict from send_telegram.run.
    """
    from scripts.delivery.send_telegram import run

    return run(chat_id=chat_id, text=text)


def notify_human(
    *,
    artifact_paths: list[Path],
    tier_decision: TierDecision,
    chat_id: str | None = None,
) -> NotificationResult:
    """Send a Telegram notification for Tier 2 human approval.

    Args:
        artifact_paths: Paths to artifacts requiring review.
        tier_decision: The tier classification decision.
        chat_id: Telegram chat ID. Falls back to VIZIER_ADMIN_CHAT_ID env var.

    Returns:
        NotificationResult with sent status, message_id, and error.

    Raises:
        ValueError: If no chat_id is provided and VIZIER_ADMIN_CHAT_ID is not set.
    """
    resolved_chat_id = chat_id or os.environ.get("VIZIER_ADMIN_CHAT_ID")
    if not resolved_chat_id:
        msg = "chat_id is required — provide directly or set VIZIER_ADMIN_CHAT_ID"
        raise ValueError(msg)

    message = _format_message(artifact_paths, tier_decision)

    try:
        result = _send_telegram(chat_id=resolved_chat_id, text=message)
        message_id = result.get("message_id")
        logger.info(
            "notification_sent",
            chat_id=resolved_chat_id,
            message_id=message_id,
        )
        return NotificationResult(
            sent=True,
            message_id=int(message_id) if message_id is not None else None,
            error=None,
        )
    except RuntimeError as exc:
        logger.warning("notification_failed", error=str(exc))
        return NotificationResult(sent=False, message_id=None, error=str(exc))
