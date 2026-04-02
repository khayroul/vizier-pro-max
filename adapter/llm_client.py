"""Shared LLM client — gateway-backed, no direct provider bypass.

All pipeline and augment LLM calls go through the local Vizier-owned
OpenAI-compatible gateway. Provider routing and usage metering happen at the
gateway boundary, not inside this client.
"""
from __future__ import annotations

import os
import re

import httpx
import structlog

from adapter.env_loader import ensure_env
from middleware.deliverable_context import (
    build_gateway_headers,
)

logger = structlog.get_logger(__name__)

# Auto-load .env from project root so gateway config is available
ensure_env()

_DEFAULT_MODEL = os.environ.get("VIZIER_LLM_MODEL", "gpt-5.4-mini")


_PREAMBLE_PATTERNS = [
    re.compile(
        r"^(?:Sure!?|Absolutely|Of course|Here(?:'s| is| you go))[^\n]*:\s*\n\n",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:Sure!?|Absolutely|Of course|Here(?:'s| is| you go))[^\n]*—[^\n]*:\s*\n\n",
        re.IGNORECASE,
    ),
]

_SIGNOFF_PATTERNS = [
    re.compile(
        r"\n\n(?:Let me know|If you(?:'d| would) like|Feel free|Hope this|I can also)[^\n]*[.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\n\n(?:Want me to|Shall I|Would you like me to)[^\n]*[.!?]?\s*$",
        re.IGNORECASE,
    ),
]


def _strip_llm_preamble(text: str) -> str:
    """Strip common LLM conversational preamble and sign-off patterns.

    Safety net for raw LLM output. The real fix is prompt discipline
    (applied per-pipeline in Sessions 2-6), but this catches residual
    conversational framing.

    Args:
        text: Raw LLM output string.

    Returns:
        Cleaned string with preamble/sign-off removed.
    """
    result = text.strip()
    if not result:
        return ""

    for pattern in _PREAMBLE_PATTERNS:
        result = pattern.sub("", result)

    for pattern in _SIGNOFF_PATTERNS:
        result = pattern.sub("", result)

    return result.strip()


def _infer_modality(messages: list[dict[str, str | list]]) -> str:
    """Infer whether this chat request is text-only or vision-enabled."""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                return "vision"
    return "chat"


def _gateway_headers(messages: list[dict[str, str | list]]) -> dict[str, str]:
    """Build gateway request headers from current Vizier context."""
    return build_gateway_headers(
        source="pipeline",
        modality=_infer_modality(messages),
    )


def _gateway_chat_endpoint() -> str:
    base_url = os.environ.get("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:11436/v1").rstrip("/")
    return f"{base_url}/chat/completions"


def chat(
    *,
    messages: list[dict[str, str | list]],
    max_tokens: int = 1024,
    timeout: float = 30.0,
    strip_preamble: bool = False,
) -> str | None:
    """Send a chat completion request via the local Vizier gateway.

    Args:
        messages: OpenAI-format message list (role + content dicts).
        max_tokens: Maximum tokens in response.
        timeout: Request timeout in seconds.

    Returns:
        Response content string, or None if the gateway call fails.
    """
    try:
        resp = httpx.post(
            _gateway_chat_endpoint(),
            headers=_gateway_headers(messages),
            json={
                "model": _DEFAULT_MODEL,
                "messages": messages,
                "stream": False,
                "max_completion_tokens": max_tokens,
            },
            timeout=max(timeout, 120.0),
        )
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("Vizier inference gateway unreachable: %s", exc)
        return None

    if resp.status_code != 200:
        logger.warning("Vizier inference gateway returned status %d", resp.status_code)
        return None

    try:
        body = resp.json()
    except ValueError as exc:
        logger.warning("Vizier inference gateway returned invalid JSON: %s", exc)
        return None

    choices = body.get("choices") or []
    if not choices:
        logger.warning("Vizier inference gateway returned no choices")
        return None

    content = choices[0].get("message", {}).get("content", "")
    if not content.strip():
        logger.warning("Vizier inference gateway returned empty content")
        return None

    logger.debug("LLM response via Vizier inference gateway (%s)", _DEFAULT_MODEL)
    return _strip_llm_preamble(content) if strip_preamble else content
