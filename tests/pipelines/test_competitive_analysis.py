"""Tests for competitive_analysis pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipelines.competitive_analysis import run


class TestCompetitiveAnalysis:
    def test_analysis_with_data(self, tmp_path: Path) -> None:
        """Pipeline with CSV data: analyze -> chart -> narrative."""
        csv_file = tmp_path / "competitors.csv"
        csv_file.write_text("company,revenue,growth\nAcme,100,5\nBeta,200,10\n")

        output_dir = str(tmp_path / "reports")

        with (
            patch("pipelines.competitive_analysis._select_analysis_operations") as mock_ops,
            patch("pipelines.competitive_analysis.analyze_run") as mock_analyze,
            patch("pipelines.competitive_analysis.chart_run") as mock_chart,
            patch("pipelines.competitive_analysis._generate_narrative") as mock_llm,
        ):
            mock_ops.return_value = [
                {"operation": "groupby", "group_column": "company", "agg_column": "revenue", "agg_function": "sum"},
            ]
            mock_analyze.return_value = {"summary": json.dumps({"Acme": 100, "Beta": 200})}
            mock_chart.return_value = {"file_path": str(tmp_path / "chart.png")}
            mock_llm.return_value = "## Analysis\nBeta leads in growth."

            result = run(
                topic="Market share",
                data_path=str(csv_file),
                output_dir=output_dir,
            )

        assert result["status"] == "completed"
        assert "report" in result
        assert result["chart_path"] is not None
        mock_analyze.assert_called_once()

    def test_analysis_without_data(self, tmp_path: Path) -> None:
        """Pipeline without data: LLM narrative only."""
        output_dir = str(tmp_path / "reports")

        with patch("pipelines.competitive_analysis._generate_narrative") as mock_llm:
            mock_llm.return_value = "## No data analysis\nGeneral insights."

            result = run(topic="AI market trends", output_dir=output_dir)

        assert result["status"] == "completed"
        assert "report" in result
        assert "chart_path" not in result

    def test_empty_topic_returns_error(self) -> None:
        """Empty topic returns error via quality gates."""
        result = run(topic="   ")
        assert "error" in result
        assert "quality_report" in result

    def test_missing_data_file_returns_error(self, tmp_path: Path) -> None:
        """Non-existent data file returns error via quality gates."""
        result = run(topic="test", data_path="/nonexistent.csv")
        assert "error" in result
        assert "quality_report" in result
