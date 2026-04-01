"""Shared LLM client — OpenAI direct, Ollama fallback.

All pipeline/augment LLM calls go through this module.
Tries OpenAI API first (OPENAI_API_KEY required).
Falls back to Qwen 3.5 9B via local Ollama if OpenAI fails.
Returns None if both are unavailable.

Cost tracking: fires middleware.cost_ledger pre/post hooks around each
provider attempt so all pipeline LLM calls are captured in the ledger.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Auto-load .env from project root so API keys are always available
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = os.environ.get("VIZIER_LLM_MODEL", "gpt-5.4-mini")

_OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
_OLLAMA_MODEL = os.environ.get("VIZIER_FALLBACK_MODEL", "qwen3.5:9b")


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


def chat(
    *,
    messages: list[dict[str, str | list]],
    max_tokens: int = 1024,
    timeout: float = 30.0,
    strip_preamble: bool = False,
) -> str | None:
    """Send a chat completion request with OpenAI -> Ollama fallback.

    Fires cost_ledger pre/post lifecycle hooks for each provider attempt
    so all LLM calls are captured in the deliverable cost ledger.

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
        return _strip_llm_preamble(result) if strip_preamble else result

    # Fallback to Ollama
    result = _try_ollama(messages, timeout)
    if result is not None:
        return _strip_llm_preamble(result) if strip_preamble else result

    logger.warning("All LLM providers unavailable")
    return None


def _fire_pre(messages: list[dict[str, str | list]], model: str) -> None:
    """Fire cost_ledger pre_llm_call hook. Non-fatal if ledger unavailable."""
    try:
        from middleware.cost_ledger import pre_llm_call  # type: ignore[import-untyped]
        pre_llm_call(messages=messages, model=model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cost_ledger pre_llm_call skipped: %s", exc)


def _fire_post(response: str | None, usage: dict[str, int]) -> None:
    """Fire cost_ledger post_llm_call hook. Non-fatal if ledger unavailable."""
    try:
        from middleware.cost_ledger import post_llm_call  # type: ignore[import-untyped]
        post_llm_call(response=response, usage=usage)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cost_ledger post_llm_call skipped: %s", exc)


def _try_openai(
    messages: list[dict[str, str | list]],
    max_tokens: int,
    timeout: float,
) -> str | None:
    """Try OpenAI API. Fires cost_ledger hooks around the call."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set, skipping OpenAI")
        return None

    _fire_pre(messages, _OPENAI_MODEL)
    try:
        resp = httpx.post(
            _OPENAI_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _OPENAI_MODEL,
                "messages": messages,
                "max_completion_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("OpenAI returned status %d", resp.status_code)
            _fire_post(None, {})
            return None

        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            logger.warning("OpenAI returned no choices")
            _fire_post(None, {})
            return None

        content = choices[0].get("message", {}).get("content", "")
        if not content.strip():
            logger.warning("OpenAI returned empty content")
            _fire_post(None, {})
            return None

        raw_usage: dict[str, Any] = body.get("usage") or {}
        usage: dict[str, int] = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0)),
            "completion_tokens": int(raw_usage.get("completion_tokens", 0)),
        }
        _fire_post(content, usage)
        logger.debug("LLM response via OpenAI (%s)", _OPENAI_MODEL)
        return content
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("OpenAI unreachable: %s", exc)
        _fire_post(None, {})
        return None


def _try_ollama(
    messages: list[dict[str, str | list]],
    timeout: float,
) -> str | None:
    """Try local Ollama (Qwen 3.5 9B). Fires cost_ledger hooks around the call."""
    _fire_pre(messages, _OLLAMA_MODEL)
    try:
        resp = httpx.post(
            _OLLAMA_ENDPOINT,
            json={
                "model": _OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 4096},
                "think": False,  # Disable Qwen thinking mode for faster responses
            },
            timeout=max(timeout, 120.0),  # Ollama can be slower, especially on first query
        )
        if resp.status_code != 200:
            logger.warning("Ollama returned status %d", resp.status_code)
            _fire_post(None, {})
            return None

        body = resp.json()
        content = body.get("message", {}).get("content", "")
        if not content.strip():
            logger.warning("Ollama returned empty content")
            _fire_post(None, {})
            return None

        usage: dict[str, int] = {
            "prompt_tokens": int(body.get("prompt_eval_count", 0)),
            "completion_tokens": int(body.get("eval_count", 0)),
        }
        _fire_post(content, usage)
        logger.debug("LLM response via Ollama (%s)", _OLLAMA_MODEL)
        return content
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("Ollama unreachable: %s", exc)
        _fire_post(None, {})
        return None
