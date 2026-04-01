"""Tests for DSPy distillation evaluator."""
from __future__ import annotations

import time
from dataclasses import fields
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from augments.distillation.evaluator import EvaluationReport, evaluate


@pytest.fixture()
def mock_program() -> MagicMock:
    """Create a mock DSPy program that returns predictable outputs."""
    program = MagicMock()
    return program


@pytest.fixture()
def sample_test_examples() -> list[dict[str, str]]:
    """Test examples with known expected outputs."""
    return [
        {"input_text": "schedule a meeting", "expected_output": "calendar"},
        {"input_text": "send an email", "expected_output": "email"},
        {"input_text": "check weather", "expected_output": "weather"},
        {"input_text": "set alarm", "expected_output": "calendar"},
        {"input_text": "write a note", "expected_output": "notes"},
    ]


class TestAccuracyCalculation:
    """Test accuracy computation with mocked DSPy program."""

    def test_accuracy_with_partial_correct(
        self,
        tmp_path: Path,
        sample_test_examples: list[dict[str, str]],
    ) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()

        mock_prog = MagicMock()
        # 3 out of 5 correct
        outputs = ["calendar", "email", "wrong", "wrong", "notes"]
        mock_prog.side_effect = [
            MagicMock(output=out) for out in outputs
        ]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=sample_test_examples,
                task_type="task_classification",
            )

        assert report.accuracy == pytest.approx(0.6)
        assert report.correct == 3
        assert report.total_examples == 5


class TestThresholdLogic:
    """Test deploy/hold recommendation based on accuracy threshold."""

    def test_above_threshold_recommends_deploy(self, tmp_path: Path) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()
        examples = [
            {"input_text": f"input_{i}", "expected_output": "calendar"}
            for i in range(10)
        ]

        mock_prog = MagicMock()
        # 9 out of 10 correct = 90%
        outputs = ["calendar"] * 9 + ["wrong"]
        mock_prog.side_effect = [
            MagicMock(output=out) for out in outputs
        ]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=examples,
                task_type="task_classification",
            )

        assert report.recommendation == "deploy"
        assert report.accuracy == pytest.approx(0.9)

    def test_below_threshold_recommends_hold(self, tmp_path: Path) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()
        examples = [
            {"input_text": f"input_{i}", "expected_output": "calendar"}
            for i in range(10)
        ]

        mock_prog = MagicMock()
        # 8 out of 10 correct = 80%
        outputs = ["calendar"] * 8 + ["wrong", "wrong"]
        mock_prog.side_effect = [
            MagicMock(output=out) for out in outputs
        ]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=examples,
                task_type="task_classification",
            )

        assert report.recommendation == "hold"
        assert report.accuracy == pytest.approx(0.8)


class TestPerClassMetrics:
    """Test per-class precision, recall, f1 computation."""

    def test_per_class_metrics_computed(self, tmp_path: Path) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()
        examples = [
            {"input_text": "a", "expected_output": "calendar"},
            {"input_text": "b", "expected_output": "calendar"},
            {"input_text": "c", "expected_output": "email"},
            {"input_text": "d", "expected_output": "email"},
        ]

        mock_prog = MagicMock()
        # Predict: calendar, email, email, calendar
        # calendar: TP=1, FP=1, FN=1 -> P=0.5, R=0.5, F1=0.5
        # email: TP=1, FP=1, FN=1 -> P=0.5, R=0.5, F1=0.5
        outputs = ["calendar", "email", "email", "calendar"]
        mock_prog.side_effect = [
            MagicMock(output=out) for out in outputs
        ]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=examples,
                task_type="task_classification",
            )

        assert "calendar" in report.per_class_metrics
        assert "email" in report.per_class_metrics
        cal = report.per_class_metrics["calendar"]
        assert cal["precision"] == pytest.approx(0.5)
        assert cal["recall"] == pytest.approx(0.5)
        assert cal["f1"] == pytest.approx(0.5)


class TestEvaluationReportFields:
    """Test that all EvaluationReport fields are populated."""

    def test_all_fields_populated(self, tmp_path: Path) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()
        examples = [{"input_text": "x", "expected_output": "calendar"}]

        mock_prog = MagicMock()
        mock_prog.side_effect = [MagicMock(output="calendar")]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=examples,
                task_type="task_classification",
            )

        for field in fields(report):
            assert getattr(report, field.name) is not None, (
                f"Field {field.name} is None"
            )


class TestEdgeCases:
    """Test edge cases: all correct, all wrong."""

    def test_all_correct_100_accuracy(self, tmp_path: Path) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()
        examples = [
            {"input_text": f"input_{i}", "expected_output": "calendar"}
            for i in range(5)
        ]

        mock_prog = MagicMock()
        mock_prog.side_effect = [
            MagicMock(output="calendar") for _ in range(5)
        ]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=examples,
                task_type="task_classification",
            )

        assert report.accuracy == pytest.approx(1.0)
        assert report.correct == 5
        assert report.recommendation == "deploy"

    def test_all_wrong_0_accuracy(self, tmp_path: Path) -> None:
        program_path = tmp_path / "program.json"
        program_path.touch()
        examples = [
            {"input_text": f"input_{i}", "expected_output": "calendar"}
            for i in range(5)
        ]

        mock_prog = MagicMock()
        mock_prog.side_effect = [
            MagicMock(output="wrong") for _ in range(5)
        ]

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_prog,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=examples,
                task_type="task_classification",
            )

        assert report.accuracy == pytest.approx(0.0)
        assert report.correct == 0
        assert report.recommendation == "hold"
