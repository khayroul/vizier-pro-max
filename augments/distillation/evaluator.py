"""Compare Qwen distilled output against GPT-5.4-mini reference.

Uses held-out test set from collector. Reports accuracy, latency,
and per-class precision/recall.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import dspy
import structlog

from augments.distillation.compiler import ToolsetClassifier

log = structlog.get_logger(__name__)

ACCURACY_THRESHOLD = 0.90


@dataclass(frozen=True)
class EvaluationReport:
    """Result of evaluating a distilled DSPy program against test examples."""

    task_type: str
    accuracy: float
    total_examples: int
    correct: int
    per_class_metrics: dict[str, dict[str, float]]
    avg_latency_ms: float
    recommendation: str


def _load_program(program_path: Path) -> ToolsetClassifier:
    """Load a compiled DSPy program from disk.

    Args:
        program_path: Path to saved DSPy program file.

    Returns:
        Loaded ToolsetClassifier instance.
    """
    program = ToolsetClassifier()
    program.load(str(program_path))
    return program


def _compute_per_class_metrics(
    expected: list[str],
    predicted: list[str],
) -> dict[str, dict[str, float]]:
    """Compute precision, recall, and F1 per class.

    Args:
        expected: List of ground-truth labels.
        predicted: List of predicted labels.

    Returns:
        Dict mapping class name to dict of precision, recall, f1.
    """
    all_classes = sorted(set(expected) | set(predicted))

    true_positives: dict[str, int] = defaultdict(int)
    false_positives: dict[str, int] = defaultdict(int)
    false_negatives: dict[str, int] = defaultdict(int)

    for exp, pred in zip(expected, predicted):
        if exp == pred:
            true_positives[exp] += 1
        else:
            false_positives[pred] += 1
            false_negatives[exp] += 1

    metrics: dict[str, dict[str, float]] = {}
    for cls in all_classes:
        tp = true_positives[cls]
        fp = false_positives[cls]
        fn = false_negatives[cls]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        metrics[cls] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    return metrics


def evaluate(
    program_path: Path,
    test_examples: list[dict[str, str]],
    task_type: str,
    model: str = "qwen3.5:9b",
) -> EvaluationReport:
    """Evaluate a compiled DSPy program against held-out test examples.

    For each test example, runs the program and compares output to expected
    via exact match (classification tasks).

    Args:
        program_path: Path to saved DSPy program.
        test_examples: List of dicts with 'input_text' and 'expected_output'.
        task_type: Task type identifier (e.g. 'task_classification').
        model: Model name for inference. Defaults to 'qwen3.5:9b'.

    Returns:
        EvaluationReport with accuracy, per-class metrics, and recommendation.
    """
    log.info(
        "starting_evaluation",
        program_path=str(program_path),
        task_type=task_type,
        num_examples=len(test_examples),
        model=model,
    )

    # Configure DSPy to use the student model for evaluation
    student_lm = dspy.LM(
        model=f"ollama_chat/{model}",
        api_base="http://localhost:11434",
        temperature=0.0,
    )
    dspy.settings.configure(lm=student_lm)

    program = _load_program(program_path)

    expected_labels: list[str] = []
    predicted_labels: list[str] = []
    correct = 0
    total_latency_ms = 0.0

    for example in test_examples:
        start = time.perf_counter()
        result = program(input_message=example["input_text"])
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        predicted = result.toolset_name
        expected = example["expected_output"]

        expected_labels.append(expected)
        predicted_labels.append(predicted)

        if predicted == expected:
            correct += 1

        total_latency_ms += elapsed_ms

    total = len(test_examples)
    accuracy = correct / total if total > 0 else 0.0
    avg_latency_ms = total_latency_ms / total if total > 0 else 0.0

    per_class_metrics = _compute_per_class_metrics(expected_labels, predicted_labels)
    recommendation = "deploy" if accuracy >= ACCURACY_THRESHOLD else "hold"

    report = EvaluationReport(
        task_type=task_type,
        accuracy=accuracy,
        total_examples=total,
        correct=correct,
        per_class_metrics=per_class_metrics,
        avg_latency_ms=avg_latency_ms,
        recommendation=recommendation,
    )

    log.info(
        "evaluation_complete",
        accuracy=accuracy,
        correct=correct,
        total=total,
        recommendation=recommendation,
    )

    return report
