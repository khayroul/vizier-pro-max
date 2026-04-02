"""Tests for poster_batch pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipelines.poster_batch import run


class TestPosterBatch:
    def test_batch_produces_posters(self, tmp_path: Path) -> None:
        """Full batch: CSV rows -> template render -> screenshots."""
        tmpl = tmp_path / "template.html"
        tmpl.write_text(
            "<html><body>"
            "<h1>{{ headline }}</h1>"
            "<p>{{ body }}</p>"
            "</body></html>"
        )

        csv_file = tmp_path / "data.csv"
        csv_file.write_text("headline,body\nHello,World\nFoo,Bar\n")

        output_dir = str(tmp_path / "posters")

        poster_0 = str(tmp_path / "posters" / "poster_0000.png")
        poster_1 = str(tmp_path / "posters" / "poster_0001.png")

        # Write minimal valid PNG bytes so score_poster_batch can open them
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with (
            patch("pipelines.poster_batch.screenshot_run") as mock_ss,
            patch("pipelines.poster_batch._generate_ai_background", return_value=None),
            patch(
                "pipelines.poster_batch._generate_image_prompt",
                return_value="soft background",
            ),
            patch(
                "pipelines.poster_batch.start_deliverable",
                return_value="test-did-0001",
            ),
            patch("pipelines.poster_batch.clear_context"),
            patch("pipelines.poster_batch.record_quality"),
            patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
            patch("pipelines.poster_batch.score_poster_batch") as mock_score,
        ):
            mock_ss.side_effect = [
                {"file_path": poster_0},
                {"file_path": poster_1},
            ]
            fake_score = MagicMock()
            fake_score.score = 8.0
            fake_score.passed = True
            mock_score.return_value = fake_score

            result = run(
                template_path=str(tmpl),
                data_path=str(csv_file),
                output_dir=output_dir,
            )

        assert result["status"] == "completed"
        assert result["count"] == 2
        assert len(result["posters"]) == 2
        assert mock_ss.call_count == 2

    def test_missing_template_raises(self, tmp_path: Path) -> None:
        """Missing template: run_with_gates returns error dict with FileNotFoundError."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n")

        with (
            patch("pipelines.poster_batch.start_deliverable", return_value="did"),
            patch("pipelines.poster_batch.clear_context"),
        ):
            result = run(template_path="/nonexistent.html", data_path=str(csv_file))

        assert "error" in result
        assert "Template not found" in result["error"]

    def test_missing_data_raises(self, tmp_path: Path) -> None:
        """Missing data file: run_with_gates returns error dict with FileNotFoundError."""
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<p>test</p>")

        with (
            patch("pipelines.poster_batch.start_deliverable", return_value="did"),
            patch("pipelines.poster_batch.clear_context"),
        ):
            result = run(template_path=str(tmpl), data_path="/nonexistent.csv")

        assert "error" in result
        assert "Data file not found" in result["error"]

    def test_no_template_path_raises(self) -> None:
        """No template_path raises ValueError."""
        with pytest.raises(ValueError, match="template_path is required"):
            run(data_path="/some/data.csv")

    def test_empty_csv(self, tmp_path: Path) -> None:
        """Empty CSV returns empty posters list."""
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<p>{{ x }}</p>")
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("x\n")

        with (
            patch("pipelines.poster_batch.start_deliverable", return_value="did"),
            patch("pipelines.poster_batch.clear_context"),
            patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
        ):
            result = run(
                template_path=str(tmpl),
                data_path=str(csv_file),
                output_dir=str(tmp_path / "out"),
            )

        assert result["count"] == 0
        assert result["posters"] == []

    def test_client_id_forwarded(self, tmp_path: Path) -> None:
        """client_id batch mode calls poster_generate and start_deliverable."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("headline,body\nTest,Body copy\n")

        poster_path = str(tmp_path / "out" / "poster_0000.png")

        with (
            patch("pipelines.poster_batch.clear_context"),
            patch("pipelines.poster_batch.start_deliverable", return_value="did") as mock_start,
            patch("pipelines.poster_batch.record_quality"),
            patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
            patch("pipelines.poster_generate.run", return_value={"poster_path": poster_path}) as mock_generate,
            patch("pipelines.poster_batch.score_poster_batch") as mock_score,
        ):
            fake_score = MagicMock()
            fake_score.score = 8.0
            fake_score.passed = True
            mock_score.return_value = fake_score

            run(
                data_path=str(csv_file),
                output_dir=str(tmp_path / "out"),
                client_id="client-abc",
            )

        mock_start.assert_called_once_with(client_id="client-abc")
        mock_generate.assert_called_once()

    def test_client_id_mode_does_not_require_template_path(self, tmp_path: Path) -> None:
        """client_id batch mode can run without a legacy template path."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("headline,body\nTest,Body copy\n")

        with (
            patch("pipelines.poster_batch.clear_context"),
            patch("pipelines.poster_batch.start_deliverable", return_value="did"),
            patch("pipelines.poster_batch.record_quality"),
            patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
            patch("pipelines.poster_generate.run", return_value={"poster_path": str(tmp_path / "poster.png")}),
            patch("pipelines.poster_batch.score_poster_batch") as mock_score,
        ):
            fake_score = MagicMock()
            fake_score.score = 8.0
            fake_score.passed = True
            mock_score.return_value = fake_score

            result = run(
                data_path=str(csv_file),
                output_dir=str(tmp_path / "out"),
                client_id="client-abc",
            )

        assert result["count"] == 1
        assert result["status"] == "completed"

    def test_gradient_fallback_used_when_ai_fails(self, tmp_path: Path) -> None:
        """When AI background fails, CSS gradient fallback is injected."""
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<body style='background:{{ background_image }}'>{{ headline }}</body>")
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("headline\nTest\n")

        captured_html: list[str] = []

        def capture_screenshot(**kwargs: object) -> dict[str, str]:
            captured_html.append(str(kwargs.get("html_content", "")))
            out = str(kwargs.get("output_path", "/tmp/p.png"))
            return {"file_path": out}

        with (
            patch("pipelines.poster_batch.screenshot_run", side_effect=capture_screenshot),
            patch("pipelines.poster_batch._generate_ai_background", return_value=None),
            patch("pipelines.poster_batch._generate_image_prompt", return_value="prompt"),
            patch("pipelines.poster_batch.start_deliverable", return_value="did"),
            patch("pipelines.poster_batch.clear_context"),
            patch("pipelines.poster_batch.record_quality"),
            patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
            patch("pipelines.poster_batch.score_poster_batch") as mock_score,
        ):
            fake_score = MagicMock()
            fake_score.score = 7.0
            fake_score.passed = True
            mock_score.return_value = fake_score

            run(
                template_path=str(tmpl),
                data_path=str(csv_file),
                output_dir=str(tmp_path / "out"),
            )

        assert len(captured_html) == 1
        assert "linear-gradient" in captured_html[0]
