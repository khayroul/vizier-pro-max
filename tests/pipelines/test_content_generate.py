"""Tests for content_generate pipeline."""
from __future__ import annotations

import json

import pytest

from pipelines.content_generate import run


class TestContentGeneratePipeline:
    def test_returns_content_for_valid_brief(self) -> None:
        result = run(brief="Write a short product description for an organic soap")
        assert "content" in result
        assert len(result["content"]) > 0

    def test_returns_error_for_empty_brief(self) -> None:
        result = run(brief="")
        assert "error" in result

    def test_returns_markdown_by_default(self) -> None:
        result = run(brief="Write a tagline for a halal restaurant")
        assert result.get("format") == "markdown"
