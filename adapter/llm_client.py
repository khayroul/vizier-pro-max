"""Shared LLM client — OpenAI direct, Ollama fallback.

All pipeline/augment LLM calls go through this module.
Tries OpenAI API first (OPENAI_API_KEY required).
Falls back to Qwen 3.5 9B via local Ollama if OpenAI fails.
Returns None if both are unavailable.
"""
from __future__ import annotations

import os

import httpx
import structlog

logger = structlog.get_logger(__name__)

_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = os.environ.get("VIZIER_LLM_MODEL", "gpt-5.4-mini")

_OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
_OLLAMA_MODEL = os.environ.get("VIZIER_FALLBACK_MODEL", "qwen3.5:9b")


def chat(
    *,
    messages: list[dict[str, str]],
    max_tokens: int = 1024,
    timeout: float = 30.0,
) -> str | None:
    """Send a chat completion request with OpenAI -> Ollama fallback.

    Args:
        messages: OpenAI-format message list (role + content dicts).
        max_tokens: Maximum tokens in response.
        timeout: Request timeout in seconds.

    Returns:
        Response content string, or None if both providers fail.
    """
    # Try OpenAI first
    result = _try_openai(messages, max_tokens, timeout)
    if result is not None:
        return result

    # Fallback to Ollama
    result = _try_ollama(messages, timeout)
    if result is not None:
        return result

    logger.warning("All LLM providers unavailable")
    return None


def _try_openai(
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout: float,
) -> str | None:
    """Try OpenAI API."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set, skipping OpenAI")
        return None

    try:
        resp = httpx.post(
            _OPENAI_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _OPENAI_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("OpenAI returned status %d", resp.status_code)
            return None

        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            logger.warning("OpenAI returned no choices")
            return None

        content = choices[0].get("message", {}).get("content", "")
        if not content.strip():
            logger.warning("OpenAI returned empty content")
            return None

        logger.debug("LLM response via OpenAI (%s)", _OPENAI_MODEL)
        return content
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("OpenAI unreachable: %s", exc)
        return None


def _try_ollama(
    messages: list[dict[str, str]],
    timeout: float,
) -> str | None:
    """Try local Ollama (Qwen 3.5 9B)."""
    try:
        resp = httpx.post(
            _OLLAMA_ENDPOINT,
            json={
                "model": _OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
            },
            timeout=max(timeout, 60.0),  # Ollama can be slower
        )
        if resp.status_code != 200:
            logger.warning("Ollama returned status %d", resp.status_code)
            return None

        body = resp.json()
        content = body.get("message", {}).get("content", "")
        if not content.strip():
            logger.warning("Ollama returned empty content")
            return None

        logger.debug("LLM response via Ollama (%s)", _OLLAMA_MODEL)
        return content
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("Ollama unreachable: %s", exc)
        return None
