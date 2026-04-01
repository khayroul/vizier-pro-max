"""Quality gate calibration — verify automated scores are trustworthy.

Runs known-good and known-bad fixtures through quality gate layers 1, 2, 4, 5
(skipping layer 3 visual QA which requires real images), compares actual
outcomes against expected outcomes, and produces a calibration report.

Report format:
    {
        "accuracy": float,
        "per_layer_metrics": {"layer": {"precision": float, "recall": float}},
        "recommended_thresholds": {"layer": suggestion},
        "test_results": [...]
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from middleware.quality_gate import (
    ValidationResult,
    log_feedback,
    validate_content_quality,
    validate_delivery,
    validate_input,
    validate_output,
)

logger = structlog.get_logger(__name__)

# Layers exercised during calibration (visual_qa excluded — needs images)
CALIBRATION_LAYERS: list[str] = [
    "input_validation",
    "output_verification",
    "content_quality",
    "delivery_verification",
]

ACCURACY_THRESHOLD: float = 0.90


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationTestCase:
    """A single calibration fixture with expected outcome."""

    name: str
    layer: str
    data: dict[str, Any]
    schema: dict[str, dict[str, Any]]
    expected_pass: bool
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationReport:
    """Full calibration report."""

    accuracy: float
    per_layer_metrics: dict[str, dict[str, float]]
    recommended_thresholds: dict[str, str]
    test_results: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def build_test_fixtures() -> list[CalibrationTestCase]:
    """Build inline test fixtures — known-good and known-bad examples.

    Returns:
        List of CalibrationTestCase instances.
    """
    fixtures: list[CalibrationTestCase] = []

    # -- Layer 1: input_validation (good) --
    fixtures.append(
        CalibrationTestCase(
            name="input_valid_complete",
            layer="input_validation",
            data={"title": "Annual Report", "pages": 12, "draft": False},
            schema={
                "title": {"type": "string", "required": True},
                "pages": {"type": "integer", "required": True},
                "draft": {"type": "boolean", "required": False},
            },
            expected_pass=True,
        )
    )

    # -- Layer 1: input_validation (bad — missing required field) --
    fixtures.append(
        CalibrationTestCase(
            name="input_missing_required",
            layer="input_validation",
            data={"pages": 5},
            schema={
                "title": {"type": "string", "required": True},
                "pages": {"type": "integer", "required": True},
            },
            expected_pass=False,
        )
    )

    # -- Layer 1: input_validation (bad — wrong type) --
    fixtures.append(
        CalibrationTestCase(
            name="input_wrong_type",
            layer="input_validation",
            data={"title": 42, "pages": "not-a-number"},
            schema={
                "title": {"type": "string", "required": True},
                "pages": {"type": "integer", "required": True},
            },
            expected_pass=False,
        )
    )

    # -- Layer 2: output_verification (good) --
    fixtures.append(
        CalibrationTestCase(
            name="output_valid",
            layer="output_verification",
            data={"result": "success", "count": 3},
            schema={
                "result": {"type": "string", "required": True},
                "count": {"type": "integer", "required": True},
            },
            expected_pass=True,
        )
    )

    # -- Layer 2: output_verification (bad — missing required output) --
    fixtures.append(
        CalibrationTestCase(
            name="output_missing_field",
            layer="output_verification",
            data={},
            schema={
                "result": {"type": "string", "required": True},
            },
            expected_pass=False,
        )
    )

    # -- Layer 2: output_verification (good — empty schema passes) --
    fixtures.append(
        CalibrationTestCase(
            name="output_empty_schema",
            layer="output_verification",
            data={"anything": "goes"},
            schema={},
            expected_pass=True,
        )
    )

    # -- Layer 4: content_quality (good — formal English) --
    fixtures.append(
        CalibrationTestCase(
            name="content_formal_english",
            layer="content_quality",
            data={
                "content": "We are pleased to present the quarterly earnings report.",
                "expected_tone": "formal",
            },
            schema={},
            expected_pass=True,
        )
    )

    # -- Layer 4: content_quality (bad — informal markers in formal context) --
    fixtures.append(
        CalibrationTestCase(
            name="content_informal_in_formal",
            layer="content_quality",
            data={
                "content": "lol omg the numbers are bruh level bad haha",
                "expected_tone": "formal",
            },
            schema={},
            expected_pass=False,
        )
    )

    # -- Layer 5: delivery_verification (good — 200 OK) --
    fixtures.append(
        CalibrationTestCase(
            name="delivery_200_ok",
            layer="delivery_verification",
            data={"status_code": 200, "channel": "telegram"},
            schema={},
            expected_pass=True,
        )
    )

    # -- Layer 5: delivery_verification (good — 201 Created) --
    fixtures.append(
        CalibrationTestCase(
            name="delivery_201_created",
            layer="delivery_verification",
            data={"status_code": 201, "channel": "whatsapp"},
            schema={},
            expected_pass=True,
        )
    )

    # -- Layer 5: delivery_verification (bad — 500 error) --
    fixtures.append(
        CalibrationTestCase(
            name="delivery_500_error",
            layer="delivery_verification",
            data={"status_code": 500, "channel": "telegram"},
            schema={},
            expected_pass=False,
        )
    )

    # -- Layer 5: delivery_verification (bad — 404 not found) --
    fixtures.append(
        CalibrationTestCase(
            name="delivery_404_not_found",
            layer="delivery_verification",
            data={"status_code": 404, "channel": "email"},
            schema={},
            expected_pass=False,
        )
    )

    return fixtures


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _run_layer(test_case: CalibrationTestCase) -> ValidationResult:
    """Run the appropriate quality gate layer for a test case.

    Args:
        test_case: The calibration test case to evaluate.

    Returns:
        ValidationResult from the quality gate layer.

    Raises:
        ValueError: If the layer is unknown.
    """
    match test_case.layer:
        case "input_validation":
            return validate_input(test_case.data, test_case.schema)
        case "output_verification":
            return validate_output(test_case.data, test_case.schema)
        case "content_quality":
            return validate_content_quality(
                content=str(test_case.data.get("content", "")),
                expected_languages=test_case.data.get("expected_languages"),
                expected_tone=test_case.data.get("expected_tone"),
            )
        case "delivery_verification":
            return validate_delivery(
                status_code=int(test_case.data.get("status_code", 0)),
                channel=str(test_case.data.get("channel", "unknown")),
            )
        case _:
            raise ValueError(f"Unknown calibration layer: {test_case.layer}")


def score_test_case(test_case: CalibrationTestCase) -> dict[str, Any]:
    """Score a single test case against the quality gate.

    Args:
        test_case: The calibration test case to score.

    Returns:
        Dict with name, expected_pass, actual_pass, errors, layer_results.
    """
    result = _run_layer(test_case)
    return {
        "name": test_case.name,
        "expected_pass": test_case.expected_pass,
        "actual_pass": result.passed,
        "errors": list(result.errors),
        "layer_results": {
            test_case.layer: {
                "passed": result.passed,
                "errors": list(result.errors),
            },
        },
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_layer_metrics(
    test_results: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Compute precision and recall per layer.

    Precision = TP / (TP + FP)  — of those predicted pass, how many truly should pass
    Recall    = TP / (TP + FN)  — of those that should pass, how many did pass

    Args:
        test_results: List of scored test case dicts.

    Returns:
        Dict mapping layer name to {"precision": float, "recall": float}.
    """
    layer_stats: dict[str, dict[str, int]] = {}

    for result in test_results:
        for layer_name, layer_data in result.get("layer_results", {}).items():
            if layer_name not in layer_stats:
                layer_stats[layer_name] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

            expected = result["expected_pass"]
            actual = layer_data["passed"]

            if expected and actual:
                layer_stats[layer_name]["tp"] += 1
            elif not expected and actual:
                layer_stats[layer_name]["fp"] += 1
            elif expected and not actual:
                layer_stats[layer_name]["fn"] += 1
            else:
                layer_stats[layer_name]["tn"] += 1

    metrics: dict[str, dict[str, float]] = {}
    for layer_name, stats in layer_stats.items():
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

        metrics[layer_name] = {
            "precision": precision,
            "recall": recall,
        }

    return metrics


def recommend_thresholds(
    accuracy: float,
    test_results: list[dict[str, Any]],
) -> dict[str, str]:
    """Recommend threshold adjustments when accuracy is below 90%.

    Args:
        accuracy: Overall calibration accuracy (0.0-1.0).
        test_results: List of scored test case dicts.

    Returns:
        Dict mapping layer name to adjustment suggestion. Empty if accuracy >= 90%.
    """
    if accuracy >= ACCURACY_THRESHOLD:
        return {}

    recommendations: dict[str, str] = {}

    # Identify layers that contributed to mismatches
    layer_mismatch_counts: dict[str, int] = {}
    for result in test_results:
        if result["expected_pass"] != result["actual_pass"]:
            for layer_name, layer_data in result.get("layer_results", {}).items():
                if layer_name not in layer_mismatch_counts:
                    layer_mismatch_counts[layer_name] = 0
                layer_mismatch_counts[layer_name] += 1

    for layer_name, count in layer_mismatch_counts.items():
        recommendations[layer_name] = (
            f"Review threshold — {count} mismatch(es) detected. "
            f"Consider relaxing validation rules for this layer."
        )

    # If no specific layer mismatches found, provide general recommendation
    if not recommendations:
        recommendations["general"] = (
            f"Overall accuracy {accuracy:.1%} is below {ACCURACY_THRESHOLD:.0%}. "
            f"Review all layer configurations."
        )

    return recommendations


# ---------------------------------------------------------------------------
# Main calibration runner
# ---------------------------------------------------------------------------


def run_calibration(
    output_path: Path | None = None,
) -> CalibrationReport:
    """Run full calibration pipeline.

    Args:
        output_path: Where to write the JSON report. Defaults to data/calibration_report.json.

    Returns:
        CalibrationReport with accuracy, per-layer metrics, and recommendations.
    """
    if output_path is None:
        output_path = Path("data/calibration_report.json")

    fixtures = build_test_fixtures()
    test_results: list[dict[str, Any]] = []

    for fixture in fixtures:
        result = score_test_case(fixture)
        test_results.append(result)
        logger.info(
            "calibration_test",
            name=fixture.name,
            expected=fixture.expected_pass,
            actual=result["actual_pass"],
            match=fixture.expected_pass == result["actual_pass"],
        )

    # Compute accuracy
    correct = sum(
        1
        for r in test_results
        if r["expected_pass"] == r["actual_pass"]
    )
    accuracy = correct / len(test_results) if test_results else 0.0

    # Compute per-layer metrics
    per_layer_metrics = compute_layer_metrics(test_results)

    # Recommend thresholds if needed
    recommended_thresholds = recommend_thresholds(accuracy, test_results)

    report = CalibrationReport(
        accuracy=accuracy,
        per_layer_metrics=per_layer_metrics,
        recommended_thresholds=recommended_thresholds,
        test_results=test_results,
    )

    # Write report to disk
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_dict: dict[str, Any] = {
        "accuracy": report.accuracy,
        "per_layer_metrics": report.per_layer_metrics,
        "recommended_thresholds": report.recommended_thresholds,
        "test_results": report.test_results,
    }
    output_path.write_text(json.dumps(report_dict, indent=2))
    logger.info(
        "calibration_complete",
        accuracy=accuracy,
        total_tests=len(test_results),
        output_path=str(output_path),
    )

    return report


if __name__ == "__main__":  # pragma: no cover
    run_calibration()
