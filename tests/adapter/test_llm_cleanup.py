"""Tests for LLM output cleanup utility."""
from __future__ import annotations

import pytest

from adapter.llm_client import _strip_llm_preamble


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Preamble removal
        ("Sure! Here's your content:\n\nActual content here.", "Actual content here."),
        ("Absolutely — here's the result:\n\nThe real output.", "The real output."),
        ("Here you go:\n\nContent body.", "Content body."),
        # Sign-off removal
        ("Good content.\n\nLet me know if you need anything else!", "Good content."),
        ("Output text.\n\nIf you'd like, I can also revise this.", "Output text."),
        # Both preamble and sign-off
        (
            "Sure! Here it is:\n\nThe deliverable.\n\nLet me know if you need changes!",
            "The deliverable.",
        ),
        # No cleanup needed — pass through unchanged
        ("Clean output with no preamble.", "Clean output with no preamble."),
        # Empty / whitespace
        ("", ""),
        ("   ", ""),
        # Single line preamble (no double newline separator)
        ("Sure! Actual content starts here.", "Sure! Actual content starts here."),
    ],
)
def test_strip_llm_preamble(raw: str, expected: str) -> None:
    assert _strip_llm_preamble(raw) == expected


def test_strip_preamble_preserves_internal_structure() -> None:
    """Multi-paragraph content should keep internal paragraphs."""
    raw = (
        "Here's your content:\n\n"
        "First paragraph.\n\n"
        "Second paragraph.\n\n"
        "Let me know if you need changes!"
    )
    result = _strip_llm_preamble(raw)
    assert "First paragraph." in result
    assert "Second paragraph." in result
    assert "Let me know" not in result


from unittest.mock import patch


def test_chat_accepts_vision_format_messages() -> None:
    """chat() must accept messages with list content blocks (vision API)."""
    from adapter.llm_client import chat

    vision_messages: list[dict[str, str | list]] = [
        {"role": "system", "content": "You are a vision model."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBOR..."},
                },
            ],
        },
    ]
    # Should not raise TypeError — we mock the HTTP call
    with patch("adapter.llm_client.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "A test image"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        result = chat(messages=vision_messages, max_tokens=100)
        assert result == "A test image"
