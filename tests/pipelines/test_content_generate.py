"""Tests for content_generate pipeline."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipelines.content_generate import run, _extract_title


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
        assert "pdf_path" not in result

    def test_pdf_format_returns_pdf_path(self) -> None:
        if shutil.which("typst") is None:
            pytest.skip("typst CLI not installed")
        result = run(
            brief="Product overview for organic honey",
            output_format="pdf",
        )
        assert result.get("format") == "pdf"
        assert "pdf_path" in result
        pdf_path = Path(result["pdf_path"])
        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        assert pdf_path.stat().st_size > 0
        # Clean up
        pdf_path.unlink(missing_ok=True)

    def test_pdf_includes_content_alongside_path(self) -> None:
        if shutil.which("typst") is None:
            pytest.skip("typst CLI not installed")
        result = run(brief="Write a report on tea", output_format="pdf")
        assert "content" in result
        assert "pdf_path" in result

    def test_pdf_graceful_error_without_typst(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        result = run(brief="Test brief", output_format="pdf")
        assert "pdf_error" in result
        assert "content" in result  # Content still returned even if PDF fails


class TestExtractTitle:
    def test_extracts_first_line(self) -> None:
        assert _extract_title("My Title\nBody text here") == "My Title"

    def test_truncates_long_titles(self) -> None:
        long_brief = "A" * 100
        assert len(_extract_title(long_brief)) == 50

    def test_handles_single_line(self) -> None:
        assert _extract_title("Short brief") == "Short brief"
