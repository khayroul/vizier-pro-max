"""Telegram mode router for personal assistant, Vizier work, and operator turns."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode


_MODE_ALIASES = {
    "/assist": "assistant",
    "/assistant": "assistant",
    "/work": "vizier_work",
    "/vizier": "vizier_work",
    "/ops": "operator",
    "/operator": "operator",
}

_OPERATOR_PATTERNS = (
    r"\bpytest\b",
    r"\btest failure\b",
    r"\btraceback\b",
    r"\bstack trace\b",
    r"\bdebug\b",
    r"\bfix\b",
    r"\brefactor\b",
    r"\bimplement\b",
    r"\bplugin\b",
    r"\bpipeline\b",
    r"\brepo\b",
    r"\bbranch\b",
    r"\bcommit\b",
    r"\bgit\b",
    r"\bfile\b",
    r"\bline\s+\d+\b",
    r"/users/executor/",
)

_VIZIER_PATTERNS = (
    r"\bposter\b",
    r"\bflyer\b",
    r"\bbanner\b",
    r"\bcreative\b",
    r"\bcampaign\b",
    r"\bproposal\b",
    r"\breport\b",
    r"\bdocument\b",
    r"\bdeck\b",
    r"\bslides\b",
    r"\bpresentation\b",
    r"\binfographic\b",
    r"\bchart\b",
    r"\bmarketing plan\b",
    r"\bcontent calendar\b",
    r"\bbrand\b",
    r"\bclient\b",
    r"\bpalette\b",
    r"\bfonts?\b",
    r"\bcta\b",
)

_ASSISTANT_PATTERNS = (
    r"\bremind\b",
    r"\breminder\b",
    r"\bschedule\b",
    r"\bcalendar\b",
    r"\bplan my day\b",
    r"\btodo\b",
    r"\bto-do\b",
    r"\bdraft a reply\b",
    r"\breply to\b",
    r"\bpersonal\b",
    r"\bmessage\b",
    r"\bcall\b",
    r"\bbuy\b",
)

_STICKY_LOOKBACK_USER_MESSAGES = 3


@dataclass(frozen=True)
class TelegramModeDecision:
    """Resolved operating mode for a Telegram turn."""

    mode: str
    source: str
    reason: str


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
    return ""


def _extract_user_messages(history: Iterable[Any]) -> list[str]:
    messages: list[str] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        if entry.get("role") != "user":
            continue
        text = _collapse_whitespace(_extract_text(entry.get("content", "")))
        if text:
            messages.append(text)
    return messages


def _explicit_mode(text: str) -> str:
    normalized = _collapse_whitespace(text).lower()
    for command, mode in _MODE_ALIASES.items():
        if normalized.startswith(command):
            return mode
    return ""


def _score_patterns(text: str, patterns: tuple[str, ...]) -> int:
    normalized = text.lower()
    return sum(1 for pattern in patterns if re.search(pattern, normalized))


def classify_telegram_mode(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]] | None = None,
    platform: str = "",
) -> TelegramModeDecision:
    """Classify the turn into assistant, Vizier work, or operator mode."""
    if platform.lower() != "telegram":
        return TelegramModeDecision(
            mode="assistant",
            source="non_telegram",
            reason="Telegram mode routing only applies on Telegram sessions.",
        )

    current_text = _collapse_whitespace(user_message)
    explicit = _explicit_mode(current_text)
    if explicit:
        return TelegramModeDecision(
            mode=explicit,
            source="explicit_command",
            reason=f"User explicitly selected {explicit} mode.",
        )

    operator_score = _score_patterns(current_text, _OPERATOR_PATTERNS)
    vizier_score = _score_patterns(current_text, _VIZIER_PATTERNS)
    assistant_score = _score_patterns(current_text, _ASSISTANT_PATTERNS)

    if operator_score >= 1 and operator_score >= vizier_score:
        return TelegramModeDecision(
            mode="operator",
            source="keyword_inference",
            reason="The turn mentions engineering or repo-maintenance work.",
        )
    if vizier_score >= 1 and vizier_score > assistant_score:
        return TelegramModeDecision(
            mode="vizier_work",
            source="keyword_inference",
            reason="The turn looks like a client or deliverable request.",
        )
    if assistant_score >= 1:
        return TelegramModeDecision(
            mode="assistant",
            source="keyword_inference",
            reason="The turn looks like a personal-assistant request.",
        )

    recent_user_messages = _extract_user_messages(conversation_history or [])
    for prior_message in reversed(recent_user_messages[-_STICKY_LOOKBACK_USER_MESSAGES:]):
        prior_explicit = _explicit_mode(prior_message)
        if prior_explicit:
            return TelegramModeDecision(
                mode=prior_explicit,
                source="sticky_override",
                reason=f"Using the most recent explicit Telegram mode override: {prior_explicit}.",
            )

    return TelegramModeDecision(
        mode="assistant",
        source="default",
        reason="Defaulting to personal assistant mode when the turn is ambiguous.",
    )


def prime_telegram_mode(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]] | None = None,
    platform: str = "",
    **_: Any,
) -> TelegramModeDecision | None:
    """Prime turn-scoped Telegram mode state before tools are resolved."""
    normalized_platform = platform.strip().lower()
    if not normalized_platform:
        clear_telegram_mode()
        return None
    if normalized_platform != "telegram":
        set_telegram_mode(platform=normalized_platform, mode="")
        return None

    decision = classify_telegram_mode(
        user_message=user_message,
        conversation_history=conversation_history,
        platform=normalized_platform,
    )
    set_telegram_mode(platform=normalized_platform, mode=decision.mode)
    return decision


def build_telegram_mode_context(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]] | None = None,
    platform: str = "",
    **_: Any,
) -> str:
    """Return mode-specific guidance for Telegram sessions."""
    decision = prime_telegram_mode(
        user_message=user_message,
        conversation_history=conversation_history,
        platform=platform,
    )
    if decision is None:
        return ""

    shared = (
        "Telegram front door mode routing is active.\n"
        f"- Current mode: {decision.mode}\n"
        f"- Routing source: {decision.source}\n"
        f"- Routing reason: {decision.reason}\n"
        "- The user can override the current mode with /assist, /work, or /ops.\n"
    )
    if decision.mode == "assistant":
        return (
            f"{shared}"
            "- Behave as a personal assistant first: help with planning, drafting replies, reminders, and everyday questions.\n"
            "- Vizier workflow tools are intentionally hidden in this mode; do not jump into deliverable generation or repo maintenance unless the user clearly asks for it.\n"
            "- If the request is truly ambiguous between personal help and deliverable work, ask one short clarification.\n"
        )
    if decision.mode == "vizier_work":
        return (
            f"{shared}"
            "- Treat this as Vizier client or deliverable work.\n"
            "- If Vizier workflow tools are not currently visible, first call switch_toolset to the closest workflow toolset: vizier-visual for posters/graphics, vizier-document for reports/proposals, vizier-content for plans/content packages, or vizier-research when the task is mainly research.\n"
            "- Use Vizier tools, reference corpora, and artifact-specific brief normalization when relevant.\n"
            "- Prefer deliverable-ready outputs over generic chatty assistance.\n"
        )
    return (
        f"{shared}"
        "- Treat this as operator mode for repo work, debugging, tests, pipeline changes, and maintenance.\n"
        "- Keep Vizier workflow toolsets off unless they are truly needed; use switch_toolset intentionally when a repo task needs a specific Vizier workflow surface.\n"
        "- Prefer codebase inspection, targeted tests, and implementation details over client-facing deliverables.\n"
        "- Do not treat engineering instructions as marketing or personal-assistant requests.\n"
    )


def register(ctx: Any) -> None:
    """Register the Telegram mode router hook."""
    ctx.register_hook("pre_tool_resolution", prime_telegram_mode)
    ctx.register_hook("pre_llm_call", build_telegram_mode_context)
