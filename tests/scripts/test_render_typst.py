"""Tests for scripts/document/render_typst.py."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.document.render_typst import render_to_pdf, _wrap_content_as_typst


class TestRenderToPdf:
    def test_renders_pdf_successfully(self, tmp_path: Path) -> None:
        if shutil.which("typst") is None:
            pytest.skip("typst CLI not installed")
        output = str(tmp_path / "test.pdf")
        result = render_to_pdf(content="Hello world", output_path=output, title="Test")
        assert "pdf_path" in result
        assert Path(result["pdf_path"]).exists()
        assert Path(result["pdf_path"]).stat().st_size > 0

    def test_returns_error_without_typst(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        result = render_to_pdf(content="Hello", title="Test")
        assert "error" in result
        assert "typst CLI not found" in result["error"]

    def test_uses_default_output_path(self) -> None:
        if shutil.which("typst") is None:
            pytest.skip("typst CLI not installed")
        result = render_to_pdf(content="Default path test", title="Auto Output")
        assert "pdf_path" in result
        path = Path(result["pdf_path"])
        assert path.exists()
        assert "auto_output" in path.name.lower()
        path.unlink(missing_ok=True)


class TestWrapContentAsTypst:
    def test_includes_title(self) -> None:
        output = _wrap_content_as_typst("Body text", "My Title")
        assert "= My Title" in output

    def test_includes_content(self) -> None:
        output = _wrap_content_as_typst("Some body content", "Title")
        assert "Some body content" in output

    def test_sets_page_margin(self) -> None:
        output = _wrap_content_as_typst("Content", "Title")
        assert "margin: 2cm" in output
