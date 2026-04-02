"""Tests for scripts/research/compose_report.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.research.compose_report import run


class TestComposeReport:
    def test_composes_markdown(self) -> None:
        result = run(
            title="Market Report",
            subtitle="Q2",
            author="Vizier",
            sections=[{"heading": "Overview", "level": 1, "body": "Hello world"}],
            output_format="markdown",
        )

        assert result["output_format"] == "markdown"
        assert "# Market Report" in result["content"]
        assert "##" not in result["content"] or "Overview" in result["content"]

    def test_composes_typst(self, tmp_path: Path) -> None:
        output = tmp_path / "report.typ"
        result = run(
            title="Market Report",
            subtitle="Q2",
            author="Vizier",
            client_name="Acme",
            date="2026-04-02",
            sections=[{"heading": "Overview", "level": 1, "body": "# Heading\nBody"}],
            output_format="typst",
            output_path=str(output),
        )

        assert result["output_format"] == "typst"
        assert result["file_path"] == str(output)
        assert output.exists()
        rendered = output.read_text(encoding="utf-8")
        assert "Market Report" in rendered
        assert "= Overview" in rendered
        assert "= Heading" in rendered

    def test_requires_sections(self) -> None:
        with pytest.raises(ValueError, match="sections is required"):
            run(title="Report", sections=[])

    def test_rejects_unknown_output_format(self) -> None:
        with pytest.raises(ValueError, match="output_format must be 'markdown' or 'typst'"):
            run(title="Report", sections=[{"heading": "A", "level": 1, "body": "B"}], output_format="html")
