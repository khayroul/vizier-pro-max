"""Telegram mode router for personal assistant, Vizier work, and operator turns."""
from __future__ import annotations

import os
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
    r"\bfailing test\b",
    r"\btest failure\b",
    r"\btraceback\b",
    r"\bstack trace\b",
    r"\bdebug\b",
    r"\binspect logs?\b",
    r"\blogs?\b",
    r"\bfix\b",
    r"\brefactor\b",
    r"\bplugin\b",
    r"\bmaintenance\b",
    r"\brepo\b",
    r"\bbranch\b",
    r"\bcommit\b",
    r"\bgit\b",
    r"\bline\s+\d+\b",
    r"/users/executor/",
)

_WORKFLOW_TOOLSET_PATTERNS = (
    ("vizier-visual", (
        r"\bposter\b",
        r"\bflyer\b",
        r"\bbanner\b",
        r"\bcreative\b",
        r"\binfographic\b",
        r"\bchart\b",
        r"\bpalette\b",
        r"\bfonts?\b",
        r"\bcta\b",
        r"\bbrand\b",
    )),
    ("vizier-document", (
        r"\bproposal\b",
        r"\breport\b",
        r"\bdocument\b",
        r"\bdeck\b",
        r"\bslides\b",
        r"\bpresentation\b",
        r"\binvoice\b",
        r"\bpdf\b",
    )),
    ("vizier-content", (
        r"\bmarketing plan\b",
        r"\bcontent calendar\b",
        r"\bcontent package\b",
        r"\bnewsletter\b",
        r"\bbrief\b",
    )),
    ("vizier-research", (
        r"\bcompetitor analysis\b",
        r"\bmarket research\b",
        r"\bresearch brief\b",
        r"\bresearch report\b",
    )),
)

_DELIVERABLE_REQUEST_PATTERNS = (
    r"\bmake\b",
    r"\bcreate\b",
    r"\bgenerate\b",
    r"\bdraft\b",
    r"\bwrite\b",
    r"\bbuild\b",
    r"\bproduce\b",
    r"\bassemble\b",
    r"\brender\b",
    r"\bi need\b",
    r"\bi want\b",
    r"\bneed a\b",
    r"\bwant a\b",
    r"\bhelp me (?:make|create|generate|draft|write|build)\b",
)

_PRODUCTION_WORKFLOW_PATTERNS = (
    r"\brun\b.*\bworkflow\b",
    r"\brun\b.*\bpipeline\b",
    r"\bproduction workflow\b",
    r"\bgenerate a client deliverable\b",
)

_POSTER_FEEDBACK_PATTERNS = (
    r"\brev(?:ise|ision)\b",
    r"\bfeedback\b",
    r"\blogo\b",
    r"\bbrand mark\b",
    r"\bduplicate\b",
    r"\bheadline\b",
    r"\blayout\b",
    r"\bhierarchy\b",
    r"\bthere are 2 text\b",
    r"\btwo text\b",
    r"\bclean(?:er| up)?\b",
    r"\bcan'?t see\b",
)

_POSTER_CRITIQUE_PATTERNS = (
    r"\bgive feedback\b",
    r"\bfeedback on\b",
    r"\bcritique\b",
    r"\breview\b",
    r"\bwhat do you think\b",
    r"\bthoughts?\b",
    r"\bgive notes\b",
)

_POSTER_CUE_PATTERNS = (
    r"\bposter\b",
    r"\bflyer\b",
    r"\bbanner\b",
    r"\bheadline\b",
    r"\blogo\b",
    r"\bbrand\b",
    r"\bmark\b",
    r"\blayout\b",
    r"\bhierarchy\b",
)

_SUPPORT_PATTERNS = (
    r"\bhelp me think\b",
    r"\bthink through\b",
    r"\bwhat should i focus on\b",
    r"\bfocus on this week\b",
    r"\bprioriti[sz]e\b",
    r"\bbusiness decision\b",
    r"\badvice\b",
    r"\bfeedback\b",
    r"\bhelp me decide\b",
    r"\bprepare for a meeting\b",
)

_ASSISTANT_PATTERNS = (
    *_SUPPORT_PATTERNS,
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
    workflow_toolset: str = ""


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


def _explicit_mode(text: str) -> tuple[str, str]:
    normalized = _collapse_whitespace(text).lower()
    for command, mode in _MODE_ALIASES.items():
        if normalized.startswith(command):
            return mode, normalized[len(command):].strip()
    return "", normalized


def _score_patterns(text: str, patterns: tuple[str, ...]) -> int:
    normalized = text.lower()
    return sum(1 for pattern in patterns if re.search(pattern, normalized))


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(re.search(pattern, normalized) for pattern in patterns)


def _infer_workflow_toolset(text: str) -> str:
    normalized = text.lower()
    for toolset_name, patterns in _WORKFLOW_TOOLSET_PATTERNS:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return toolset_name
    return ""


def _looks_like_support_request(text: str) -> bool:
    return _matches_any(text, _ASSISTANT_PATTERNS)


def _looks_like_vizier_work_request(text: str) -> bool:
    workflow_toolset = _infer_workflow_toolset(text)
    if not workflow_toolset:
        return False
    if _matches_any(text, _PRODUCTION_WORKFLOW_PATTERNS):
        return True
    if _looks_like_support_request(text):
        return False
    return _matches_any(text, _DELIVERABLE_REQUEST_PATTERNS)


def _has_active_poster_session() -> bool:
    return bool(os.getenv("HERMES_TELEGRAM_POSTER_PATH", "").strip())


def _looks_like_poster_feedback_request(text: str) -> bool:
    return _matches_any(text, _POSTER_FEEDBACK_PATTERNS)


def _looks_like_poster_critique_request(text: str) -> bool:
    return _matches_any(text, _POSTER_CRITIQUE_PATTERNS) and _matches_any(
        text,
        _POSTER_CUE_PATTERNS,
    )


def _auto_activate_workflow_toolset(
    *,
    decision: TelegramModeDecision,
    agent: Any | None,
) -> None:
    if decision.mode != "vizier_work" or not decision.workflow_toolset:
        return
    if agent is None:
        return

    enabled_toolsets = getattr(agent, "enabled_toolsets", None)
    if enabled_toolsets is None:
        return

    current_toolsets = list(enabled_toolsets)
    if decision.workflow_toolset in current_toolsets:
        return

    from plugins.switch_toolset import build_switched_toolsets

    agent.enabled_toolsets = build_switched_toolsets(
        current_toolsets,
        decision.workflow_toolset,
    )


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
    explicit, explicit_remainder = _explicit_mode(current_text)
    if explicit:
        return TelegramModeDecision(
            mode=explicit,
            source="explicit_command",
            reason=f"User explicitly selected {explicit} mode.",
            workflow_toolset=_infer_workflow_toolset(explicit_remainder),
        )

    operator_score = _score_patterns(current_text, _OPERATOR_PATTERNS)
    if operator_score >= 1:
        return TelegramModeDecision(
            mode="operator",
            source="keyword_inference",
            reason="The turn mentions engineering or repo-maintenance work.",
        )
    if _has_active_poster_session() and _looks_like_poster_critique_request(current_text):
        return TelegramModeDecision(
            mode="assistant",
            source="poster_session_critique",
            reason="The turn asks for critique on the current poster without clearly requesting changes.",
        )
    if _has_active_poster_session() and _looks_like_poster_feedback_request(current_text):
        return TelegramModeDecision(
            mode="vizier_work",
            source="poster_session_feedback",
            reason="The turn looks like feedback on the latest poster in this Telegram session.",
            workflow_toolset="vizier-visual",
        )
    if _looks_like_vizier_work_request(current_text):
        return TelegramModeDecision(
            mode="vizier_work",
            source="keyword_inference",
            reason="The turn is clearly asking for a polished deliverable or Vizier workflow run.",
            workflow_toolset=_infer_workflow_toolset(current_text),
        )
    if _looks_like_support_request(current_text):
        return TelegramModeDecision(
            mode="assistant",
            source="keyword_inference",
            reason="The turn is asking for support, planning, thinking, or drafting help.",
        )

    recent_user_messages = _extract_user_messages(conversation_history or [])
    for prior_message in reversed(recent_user_messages[-_STICKY_LOOKBACK_USER_MESSAGES:]):
        prior_explicit, _ = _explicit_mode(prior_message)
        if prior_explicit:
            return TelegramModeDecision(
                mode=prior_explicit,
                source="sticky_override",
                reason=f"Using the most recent explicit Telegram mode override: {prior_explicit}.",
            )

    return TelegramModeDecision(
        mode="assistant",
        source="default",
        reason="Defaulting to assistant mode for ambiguous life or work support requests.",
    )


def prime_telegram_mode(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]] | None = None,
    platform: str = "",
    agent: Any | None = None,
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
    _auto_activate_workflow_toolset(decision=decision, agent=agent)
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
            "- Behave as an assistant for both personal life and professional life: help with planning, prioritization, drafting replies, thinking through decisions, reminders, and everyday questions.\n"
            "- Vizier workflow tools are intentionally hidden in this mode; do not jump into deliverable generation or repo maintenance unless the user clearly asks for it.\n"
            "- If the request is truly ambiguous between personal help and deliverable work, ask one short clarification.\n"
        )
    if decision.mode == "vizier_work":
        revision_line = (
            "- If this is feedback on the latest poster in the Telegram session, explain the planned deltas in one short sentence and then use revise_poster.\n"
            if decision.source == "poster_session_feedback"
            else ""
        )
        activation_line = (
            f"- The matching Vizier workflow surface should already be active for this turn: {decision.workflow_toolset}.\n"
            if decision.workflow_toolset
            else "- When the target deliverable is clear, the matching Vizier workflow surface can activate automatically; otherwise use switch_toolset to choose the right workflow surface.\n"
        )
        return (
            f"{shared}"
            "- Treat this as Vizier client or deliverable work.\n"
            f"{revision_line}"
            f"{activation_line}"
            "- Use switch_toolset only if you intentionally want a different Vizier workflow surface than the one implied by the request.\n"
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
