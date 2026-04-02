"""Tests for scripts/document/render_template.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.document.render_template import run


SAMPLE_BRAND = {
    "primary_color": "#112233",
    "secondary_color": "#f4f5f6",
    "accent_color": "#ff3366",
    "headline_font": "Georgia",
    "body_font": "Inter",
}

SAMPLE_CONTENT = {
    "title": "Quarterly Report",
    "subtitle": "Growth snapshot",
    "author": "Vizier",
    "date": "2026-04-02",
    "executive_summary": "<p>Summary</p>",
    "body": "<h2>Body</h2><p>Detail</p>",
    "footer": "Confidential",
    "company_name": "Vizier",
    "invoice_number": "INV-001",
    "client_name": "Client",
    "article_body": "<p>Article body</p>",
    "chapter_body": "<p>Chapter body</p>",
}


class TestRenderTemplate:
    @pytest.mark.parametrize(
        "template_name",
        ["article", "ebook-chapter", "invoice", "one-pager", "proposal", "report"],
    )
    def test_renders_all_document_templates(
        self, tmp_path: Path, template_name: str
    ) -> None:
        output_path = tmp_path / f"{template_name}.html"
        result = run(
            template_name=template_name,
            content=SAMPLE_CONTENT,
            brand=SAMPLE_BRAND,
            output_path=str(output_path),
        )

        assert result["filled_template_path"] == str(output_path)
        assert result["html_length"] > 0
        assert output_path.exists()
        assert "<html" in output_path.read_text(encoding="utf-8").lower()

    def test_brand_variables_are_injected_into_root(self, tmp_path: Path) -> None:
        output_path = tmp_path / "report.html"
        run(
            template_name="report",
            content=SAMPLE_CONTENT,
            brand=SAMPLE_BRAND,
            output_path=str(output_path),
        )
        html = output_path.read_text(encoding="utf-8")

        assert "#112233" in html
        assert "#ff3366" in html
        assert "Georgia" in html
        assert "Inter" in html

    def test_missing_optional_placeholders_fall_back_cleanly(self, tmp_path: Path) -> None:
        output_path = tmp_path / "minimal.html"
        run(
            template_name="report",
            content={"title": "Minimal"},
            brand={},
            output_path=str(output_path),
        )
        html = output_path.read_text(encoding="utf-8")

        assert "--primary:      #1A1A2E;" in html
        assert "--font-body:    system-ui, -apple-system, sans-serif;" in html
