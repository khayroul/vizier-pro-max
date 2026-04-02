"""Per-turn Telegram mode state used by routing and tool gating."""
from __future__ import annotations

import os
from contextvars import ContextVar

_CURRENT_TELEGRAM_MODE: ContextVar[str] = ContextVar(
    "vizier_current_telegram_mode",
    default="",
)
_CURRENT_PLATFORM: ContextVar[str] = ContextVar(
    "vizier_current_platform",
    default="",
)


def _front_door_enabled() -> bool:
    explicit = os.getenv("VIZIER_TELEGRAM_FRONT_DOOR", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if explicit:
        return True
    return bool(
        os.getenv("MESSAGING_CWD", "").strip()
        and os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )


def set_telegram_mode(*, platform: str, mode: str) -> None:
    """Persist the current Telegram routing decision for this execution context."""
    _CURRENT_PLATFORM.set(platform.strip().lower())
    _CURRENT_TELEGRAM_MODE.set(mode.strip())


def clear_telegram_mode() -> None:
    """Clear the current routing decision."""
    _CURRENT_PLATFORM.set("")
    _CURRENT_TELEGRAM_MODE.set("")


def get_telegram_mode() -> str:
    """Return the current Telegram routing mode, defaulting to assistant for the front door."""
    mode = _CURRENT_TELEGRAM_MODE.get().strip()
    if mode:
        return mode
    if _front_door_enabled():
        return "assistant"
    return ""


def telegram_mode_allows(*allowed_modes: str) -> bool:
    """Return whether the current Telegram mode should see a gated tool.

    Non-Telegram contexts remain unaffected. For the Telegram front door,
    tools default to assistant mode until a per-turn decision is set.
    """
    platform = _CURRENT_PLATFORM.get().strip().lower()
    if platform and platform != "telegram":
        return True
    if not platform and not _front_door_enabled():
        return True
    if not allowed_modes:
        return True
    return get_telegram_mode() in allowed_modes
