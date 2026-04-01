"""Pipeline runner — wraps pipeline functions with quality gates.

Runs L1 (input validation), pipeline execution, L2 (output validation),
optional L4 (content quality), and L6 (feedback logging) around any
pipeline function, returning a unified result with quality_report.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

import structlog

from middleware.quality_gate import (
    ValidationResult,
    log_feedback,
    validate_content_quality,
    validate_input,
    validate_output,
)

logger = structlog.get_logger(__name__)


def _result_to_dict(vr: ValidationResult) -> dict[str, Any]:
    """Convert a ValidationResult dataclass to a plain dict."""
    return {
        "passed": vr.passed,
        "errors": list(vr.errors),
        "layer": vr.layer,
    }


def _log_feedback_result(
    pipeline_name: str,
    layer: int,
    score: float,
    passed: bool,
    session_id: str,
) -> ValidationResult:
    """Log feedback via quality_gate.log_feedback and return the result."""
    return log_feedback(
        tool_name=pipeline_name,
        layer=layer,
        score=score,
        passed=passed,
        session_id=session_id,
    )


def run_with_gates(
    *,
    pipeline_fn: Callable[[dict[str, Any]], dict[str, Any]],
    inputs: dict[str, Any],
    input_schema: dict[str, dict[str, Any]],
    output_schema: dict[str, dict[str, Any]],
    quality_config: dict[str, Any] | None = None,
    pipeline_name: str = "unknown",
) -> dict[str, Any]:
    """Run a pipeline function wrapped with quality gate validation.

    Args:
        pipeline_fn: The pipeline callable to execute.
        inputs: Input data dict to pass to the pipeline.
        input_schema: Schema for L1 input validation.
        output_schema: Schema for L2 output validation.
        quality_config: Optional config for additional quality layers.
            If ``{"L4": {...}}`` is present, content quality is checked.
        pipeline_name: Name used for feedback logging.

    Returns:
        Dict with pipeline results merged with a ``quality_report`` key.
    """
    config = quality_config or {}
    report: dict[str, dict[str, Any]] = {}
    session_id = str(uuid.uuid4())

    # L1: Input validation (always)
    l1_result = validate_input(inputs, input_schema)
    report["L1"] = _result_to_dict(l1_result)

    if not l1_result.passed:
        # L6: Feedback even on early exit
        l6_result = _log_feedback_result(
            pipeline_name=pipeline_name,
            layer=1,
            score=0.0,
            passed=False,
            session_id=session_id,
        )
        report["L6"] = _result_to_dict(l6_result)
        return {
            "error": f"Input validation failed: {l1_result.errors}",
            "quality_report": report,
        }

    # Run pipeline
    try:
        pipeline_output = pipeline_fn(inputs)
    except Exception as exc:
        l6_result = _log_feedback_result(
            pipeline_name=pipeline_name,
            layer=0,
            score=0.0,
            passed=False,
            session_id=session_id,
        )
        report["L6"] = _result_to_dict(l6_result)
        return {
            "error": f"Pipeline execution failed: {exc}",
            "quality_report": report,
        }

    # L2: Output validation (always)
    l2_result = validate_output(pipeline_output, output_schema)
    report["L2"] = _result_to_dict(l2_result)

    # L4: Content quality (opt-in)
    if "L4" in config:
        l4_config = config["L4"]
        content = str(pipeline_output.get("content", ""))
        l4_result = validate_content_quality(
            content=content,
            expected_languages=l4_config.get("expected_languages"),
            expected_tone=l4_config.get("expected_tone"),
        )
        report["L4"] = _result_to_dict(l4_result)

    # L6: Feedback (always)
    all_passed = all(layer.get("passed", False) for layer in report.values())
    l6_result = _log_feedback_result(
        pipeline_name=pipeline_name,
        layer=6,
        score=1.0 if all_passed else 0.0,
        passed=all_passed,
        session_id=session_id,
    )
    report["L6"] = _result_to_dict(l6_result)

    return {**pipeline_output, "quality_report": report}
