"""Tests for presentation_deck_generate pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipelines.presentation_deck_generate import run


class TestPresentationDeckGenerate:
    def test_brief_mode_calls_gamma_directly(self, tmp_path: Path) -> None:
        fake_gamma_result = {
            "generation_id": "gamma_1",
            "status": "completed",
            "gamma_url": "https://gamma.app/docs/gamma_1",
            "file_path": str(tmp_path / "deck.pdf"),
        }
        Path(fake_gamma_result["file_path"]).write_bytes(b"%PDF-1.4")

        with patch(
            "pipelines.presentation_deck_generate.gamma_generate_run",
            return_value=fake_gamma_result,
        ) as gamma_mock:
            result = run(
                title="Client Strategy Deck",
                brief="Turn this strategy into a board-ready client deck.",
                output_dir=str(tmp_path),
                gamma_theme_id="theme_1",
            )

        assert result["status"] == "completed"
        assert result["pipeline"] == "presentation_deck_generate"
        assert result["source_mode"] == "brief"
        assert Path(result["source_markdown_path"]).exists()
        assert result["gamma_url"] == "https://gamma.app/docs/gamma_1"
        assert Path(result["gamma_file_path"]).exists()
        gamma_kwargs = gamma_mock.call_args.kwargs
        assert gamma_kwargs["text_mode"] == "generate"
        assert gamma_kwargs["format"] == "presentation"
        assert gamma_kwargs["theme_id"] == "theme_1"
        assert gamma_kwargs["card_dimensions"] == "16x9"
        assert result["quality_report"]["passed"] is True

    def test_structured_mode_delegates_to_structured_nonfiction(self, tmp_path: Path) -> None:
        fake_result = {
            "status": "completed",
            "title": "Client Strategy Deck",
            "gamma_url": "https://gamma.app/docs/gamma_2",
            "gamma_file_path": str(tmp_path / "deck.pdf"),
            "documents": [],
        }
        with patch(
            "pipelines.presentation_deck_generate.run_structured_nonfiction",
            return_value=fake_result,
        ) as structured_mock:
            result = run(
                title="Client Strategy Deck",
                author="Vizier",
                sections=[
                    {"heading": "Executive Summary", "body": "Summary"},
                    {"heading": "Plan", "body": "Plan"},
                    {"heading": "Next Steps", "body": "Next"},
                ],
                output_dir=str(tmp_path),
                gamma_template_id="gamma_template_123",
                gamma_export_as="pptx",
            )

        assert result["source_mode"] == "structured"
        assert result["pipeline"] == "presentation_deck_generate"
        kwargs = structured_mock.call_args.kwargs
        assert kwargs["export_gamma"] is True
        assert kwargs["gamma_template_id"] == "gamma_template_123"
        assert kwargs["gamma_export_as"] == "pptx"
        assert kwargs["gamma_text_mode"] == "condense"
