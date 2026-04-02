"""Quality tests for content_generate pipeline improvements."""
from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest


def _mock_llm_json_response() -> str:
    """Simulate the new JSON-structured LLM response."""
    return json.dumps({
        "title": "Discover Ethiopian Yirgacheffe at Our PJ Cafe",
        "body": (
            "Looking for the perfect cup to start your week? "
            "Our new single-origin Ethiopian Yirgacheffe beans bring "
            "bright citrus notes and a floral finish that coffee "
            "enthusiasts can't stop talking about.\n\n"
            "Visit our Petaling Jaya cafe this weekend for a free "
            "tasting event — perfect for young professionals who "
            "appreciate quality in every sip."
        ),
        "hashtags": ["#MalaysianCoffee", "#PetalingJaya", "#CoffeeTasting"],
    })


def test_title_is_not_truncated_brief() -> None:
    """Title must come from LLM output, not first 50 chars of brief."""
    from pipelines.content_generate import _extract_title_from_response

    response = _mock_llm_json_response()
    title = _extract_title_from_response(response)
    assert "Discover" in title or "Ethiopian" in title
    assert len(title) > 10


def test_extract_title_fallback_from_body() -> None:
    """If JSON parsing fails, extract title from first heading or line."""
    from pipelines.content_generate import _extract_title_from_response

    plain_text = "# My Great Title\n\nSome body content here."
    title = _extract_title_from_response(plain_text)
    assert title == "My Great Title"


def test_extract_title_fallback_plain() -> None:
    """Plain text without heading uses first sentence."""
    from pipelines.content_generate import _extract_title_from_response

    plain = "This is a great post about coffee. More details follow."
    title = _extract_title_from_response(plain)
    assert "coffee" in title.lower()


def test_system_prompt_requests_json() -> None:
    """System prompt must instruct JSON output format."""
    from pipelines.content_generate import _SYSTEM_PROMPT

    assert "json" in _SYSTEM_PROMPT.lower() or "JSON" in _SYSTEM_PROMPT


def test_no_preamble_in_content() -> None:
    """Generated content must not contain LLM conversational artifacts."""
    preamble_patterns = [
        r"^Sure",
        r"^Absolutely",
        r"^Here(?:'s| is| you go)",
        r"Let me know if",
        r"I can also",
        r"Hope this helps",
    ]
    from adapter.llm_client import _strip_llm_preamble

    dirty = (
        "Sure! Here's your LinkedIn post:\n\n"
        "Great content here.\n\n"
        "Let me know if you need changes!"
    )
    clean = _strip_llm_preamble(dirty)
    for pattern in preamble_patterns:
        assert not re.search(
            pattern, clean, re.IGNORECASE
        ), f"Found preamble: {pattern}"


def test_run_returns_quality_report() -> None:
    """Pipeline result must include quality_report from run_with_gates."""
    from pipelines.content_generate import run as content_run

    with patch(
        "pipelines.content_generate.llm_chat",
        return_value=_mock_llm_json_response(),
    ):
        result = content_run(
            brief="Test brief for quality check",
            output_format="markdown",
        )
        assert "quality_report" in result
        assert result["quality_report"]["L1"]["passed"] is True


def test_extract_structured_response_parses_json() -> None:
    """_extract_structured_response must parse JSON into ContentResponse."""
    from pipelines.content_generate import _extract_structured_response, ContentResponse

    raw = json.dumps({
        "title": "Test Title",
        "body": "Test body content",
        "hashtags": ["#one", "#two", "#three"],
    })
    result = _extract_structured_response(raw)
    assert isinstance(result, ContentResponse)
    assert result.title == "Test Title"
    assert result.body == "Test body content"
    assert result.hashtags == ["#one", "#two", "#three"]


def test_extract_structured_response_fallback() -> None:
    """_extract_structured_response must fall back gracefully for plain text."""
    from pipelines.content_generate import _extract_structured_response

    result = _extract_structured_response("Just plain text content.")
    assert result.body == "Just plain text content."
    assert len(result.title) > 0


def test_render_to_pdf_accepts_accent_and_hashtags() -> None:
    """render_to_pdf signature must include accent_color and hashtags params."""
    import inspect
    from scripts.document.render_typst import render_to_pdf

    sig = inspect.signature(render_to_pdf)
    assert "accent_color" in sig.parameters
    assert "hashtags" in sig.parameters
