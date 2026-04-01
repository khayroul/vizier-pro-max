"""Tests for content_generate pipeline with real/mocked LLM."""
from __future__ import annotations

from unittest.mock import patch

from pipelines.content_generate import run


class TestContentGenerateLLM:
    """Tests for LLM integration in the content generation pipeline."""

    def test_calls_llm_when_available(self) -> None:
        """Pipeline calls LLM and returns generated content."""
        with patch(
            "pipelines.content_generate._call_llm",
            return_value="Selamat pagi! Here is your post about Hari Raya.",
        ):
            result = run(brief="Write a Hari Raya greeting post")
        assert "Selamat pagi" in result["content"]
        assert "[Generated content for:" not in result["content"]

    def test_falls_back_to_stub_on_llm_error(self) -> None:
        """Pipeline falls back to stub if LLM is unavailable."""
        with patch("pipelines.content_generate._call_llm", return_value=None):
            result = run(brief="Write a product launch post")
        assert "[Generated content for:" in result["content"]
