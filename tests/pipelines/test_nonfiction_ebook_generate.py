"""Tests for nonfiction_ebook_generate pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipelines.nonfiction_ebook_generate import run


def _write_fake_pdf(path: str) -> None:
    Path(path).write_bytes(b"%PDF-1.4")


def _write_fake_epub(path: str) -> None:
    Path(path).write_bytes(b"epub")


def _fake_chart_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    Path(output_path).write_bytes(b"png")
    return {"file_path": output_path}


def _fake_pdf_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    _write_fake_pdf(output_path)
    return {"file_path": output_path}


def _fake_epub_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    _write_fake_epub(output_path)
    return {"file_path": output_path}


class TestNonfictionEbookGenerate:
    def test_generates_exports_and_charts(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.nonfiction_ebook_generate.chart_run",
                side_effect=_fake_chart_run,
            ),
            patch(
                "pipelines.nonfiction_ebook_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.nonfiction_ebook_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run(
                title="SME Growth Playbook",
                author="Vizier",
                sections=[
                    {"heading": "Overview", "body": "Growth summary", "callout": "Key takeaways"},
                    {"heading": "Market Trends", "body": "Market analysis"},
                    {"heading": "Recommendations", "body": "Action plan"},
                ],
                charts=[
                    {
                        "section_heading": "Market Trends",
                        "chart_type": "bar",
                        "data": {"labels": ["A", "B"], "values": [10, 20]},
                        "title": "Trend Lift",
                    }
                ],
                output_dir=str(tmp_path / "book"),
            )

        assert result["status"] == "completed"
        assert result["section_count"] == 3
        assert result["chart_count"] == 1
        assert Path(result["html_path"]).exists()
        assert Path(result["markdown_path"]).exists()
        assert Path(result["pdf_path"]).exists()
        assert Path(result["epub_path"]).exists()
        assert result["quality_report"]["passed"] is True

    def test_rejects_chart_with_unknown_section(self, tmp_path: Path) -> None:
        try:
            run(
                title="SME Growth Playbook",
                author="Vizier",
                sections=[{"heading": "Overview", "body": "Growth summary"}],
                charts=[
                    {
                        "section_heading": "Missing",
                        "chart_type": "bar",
                        "data": {"labels": ["A"], "values": [1]},
                    }
                ],
                output_dir=str(tmp_path / "book"),
                export_pdf=False,
                export_epub=False,
            )
        except ValueError as exc:
            assert "section_heading" in str(exc)
        else:
            raise AssertionError("Expected ValueError")
