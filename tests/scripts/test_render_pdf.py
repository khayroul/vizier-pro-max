"""Tests for scripts/document/render_pdf.py."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


class _FakeHtml:
    last_string: str | None = None
    last_filename: str | None = None
    last_pdf_output: str | None = None

    def __init__(self, *, string: str | None = None, filename: str | None = None) -> None:
        _FakeHtml.last_string = string
        _FakeHtml.last_filename = filename

    def write_pdf(self, output_path: str) -> None:
        _FakeHtml.last_pdf_output = output_path
        Path(output_path).write_bytes(b"%PDF-1.4")


class TestRenderPdf:
    def test_renders_from_html_content(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_module = types.SimpleNamespace(HTML=_FakeHtml)
        monkeypatch.setitem(sys.modules, "weasyprint", fake_module)

        from scripts.document.render_pdf import run

        output = tmp_path / "output.pdf"
        result = run(html_content="<h1>Hello</h1>", output_path=str(output))

        assert result["file_path"] == str(output)
        assert output.exists()
        assert _FakeHtml.last_string == "<h1>Hello</h1>"
        assert _FakeHtml.last_filename is None

    def test_renders_from_input_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_module = types.SimpleNamespace(HTML=_FakeHtml)
        monkeypatch.setitem(sys.modules, "weasyprint", fake_module)

        from scripts.document.render_pdf import run

        html_file = tmp_path / "input.html"
        html_file.write_text("<h1>Hello</h1>", encoding="utf-8")
        output = tmp_path / "output.pdf"
        run(input_path=str(html_file), output_path=str(output))

        assert _FakeHtml.last_filename == str(html_file)

    def test_requires_html_source(self, tmp_path: Path) -> None:
        from scripts.document.render_pdf import run

        with pytest.raises(ValueError, match="html_content or input_path is required"):
            run(output_path=str(tmp_path / "out.pdf"))
