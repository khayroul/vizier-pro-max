"""Tests for quality gate calibration script.

Verifies that the calibration pipeline:
- Scores known-good fixtures well
- Scores known-bad fixtures poorly
- Produces a calibration report with all required fields
- Recommends threshold adjustments when accuracy is low
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.bootstrap.calibrate_quality_gate import (
    CalibrationReport,
    CalibrationTestCase,
    build_test_fixtures,
    compute_layer_metrics,
    recommend_thresholds,
    run_calibration,
    score_test_case,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def good_fixtures() -> list[CalibrationTestCase]:
    """Return only the known-good fixtures from the fixture builder."""
    return [tc for tc in build_test_fixtures() if tc.expected_pass]


@pytest.fixture
def bad_fixtures() -> list[CalibrationTestCase]:
    """Return only the known-bad fixtures from the fixture builder."""
    return [tc for tc in build_test_fixtures() if not tc.expected_pass]


# ---------------------------------------------------------------------------
# Known-good fixtures score well
# ---------------------------------------------------------------------------


class TestGoodFixtures:
    """Known-good fixtures should pass all relevant layers."""

    def test_good_fixtures_exist(self, good_fixtures: list[CalibrationTestCase]) -> None:
        assert len(good_fixtures) > 0, "Must have at least one good fixture"

    def test_good_fixtures_score_pass(
        self, good_fixtures: list[CalibrationTestCase]
    ) -> None:
        for fixture in good_fixtures:
            result = score_test_case(fixture)
            assert result["actual_pass"], (
                f"Good fixture '{fixture.name}' should pass, "
                f"but got errors: {result['errors']}"
            )


# ---------------------------------------------------------------------------
# Known-bad fixtures score poorly
# ---------------------------------------------------------------------------


class TestBadFixtures:
    """Known-bad fixtures should fail at least one layer."""

    def test_bad_fixtures_exist(self, bad_fixtures: list[CalibrationTestCase]) -> None:
        assert len(bad_fixtures) > 0, "Must have at least one bad fixture"

    def test_bad_fixtures_score_fail(
        self, bad_fixtures: list[CalibrationTestCase]
    ) -> None:
        for fixture in bad_fixtures:
            result = score_test_case(fixture)
            assert not result["actual_pass"], (
                f"Bad fixture '{fixture.name}' should fail, but it passed"
            )


# ---------------------------------------------------------------------------
# Calibration report structure
# ---------------------------------------------------------------------------


class TestCalibrationReport:
    """The calibration report must contain all required fields."""

    def test_report_has_required_fields(self, tmp_path: Path) -> None:
        report = run_calibration(output_path=tmp_path / "report.json")

        assert isinstance(report.accuracy, float)
        assert 0.0 <= report.accuracy <= 1.0

        assert isinstance(report.per_layer_metrics, dict)
        assert len(report.per_layer_metrics) > 0

        assert isinstance(report.recommended_thresholds, dict)
        assert isinstance(report.test_results, list)
        assert len(report.test_results) > 0

    def test_per_layer_metrics_have_precision_recall(self, tmp_path: Path) -> None:
        report = run_calibration(output_path=tmp_path / "report.json")

        for layer_name, metrics in report.per_layer_metrics.items():
            assert "precision" in metrics, f"Missing precision for {layer_name}"
            assert "recall" in metrics, f"Missing recall for {layer_name}"
            assert 0.0 <= metrics["precision"] <= 1.0
            assert 0.0 <= metrics["recall"] <= 1.0

    def test_report_written_to_file(self, tmp_path: Path) -> None:
        output_path = tmp_path / "report.json"
        run_calibration(output_path=output_path)

        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert "accuracy" in data
        assert "per_layer_metrics" in data
        assert "recommended_thresholds" in data
        assert "test_results" in data


# ---------------------------------------------------------------------------
# Threshold recommendation logic
# ---------------------------------------------------------------------------


class TestThresholdRecommendation:
    """When accuracy < 90%, the system should recommend adjustments."""

    def test_low_accuracy_triggers_recommendations(self) -> None:
        """If accuracy is below 90%, recommended_thresholds should be non-empty."""
        # Simulate results where some predictions are wrong
        test_results: list[dict[str, Any]] = [
            {"name": f"case_{i}", "expected_pass": True, "actual_pass": True, "layer_results": {}}
            for i in range(7)
        ] + [
            {"name": f"bad_{i}", "expected_pass": True, "actual_pass": False, "layer_results": {
                "input_validation": {"passed": False, "errors": ["error"]},
            }}
            for i in range(3)
        ]

        accuracy = 0.70
        recommendations = recommend_thresholds(accuracy, test_results)
        assert len(recommendations) > 0, (
            "Should recommend adjustments when accuracy < 90%"
        )

    def test_high_accuracy_no_recommendations(self) -> None:
        """If accuracy >= 90%, no threshold adjustments needed."""
        test_results: list[dict[str, Any]] = [
            {"name": f"case_{i}", "expected_pass": True, "actual_pass": True, "layer_results": {}}
            for i in range(10)
        ]

        accuracy = 1.0
        recommendations = recommend_thresholds(accuracy, test_results)
        assert len(recommendations) == 0, (
            "Should not recommend adjustments when accuracy >= 90%"
        )


# ---------------------------------------------------------------------------
# Layer metrics computation
# ---------------------------------------------------------------------------


class TestLayerMetrics:
    """Verify precision/recall computation per layer."""

    def test_perfect_layer(self) -> None:
        """A layer that correctly identifies all pass/fail cases."""
        test_results: list[dict[str, Any]] = [
            {
                "name": "good_1",
                "expected_pass": True,
                "actual_pass": True,
                "layer_results": {"input_validation": {"passed": True, "errors": []}},
            },
            {
                "name": "bad_1",
                "expected_pass": False,
                "actual_pass": False,
                "layer_results": {"input_validation": {"passed": False, "errors": ["err"]}},
            },
        ]
        metrics = compute_layer_metrics(test_results)
        assert "input_validation" in metrics
        assert metrics["input_validation"]["precision"] == 1.0
        assert metrics["input_validation"]["recall"] == 1.0

    def test_empty_results(self) -> None:
        """No test results should yield empty metrics."""
        metrics = compute_layer_metrics([])
        assert metrics == {}
