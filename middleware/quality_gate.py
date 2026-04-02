"""Quality Gate — Layers 1-6.

Called explicitly by pipeline scripts and adapter/executor.py.
Not a model-callable tool — this is middleware.

Gate 1: Layers 1-2 (pydantic-based validation)
Gate 2+: Layers 3-6 (visual QA, content quality, delivery, feedback)
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from scripts.visual.calculate_delta import calculate_delta

logger = structlog.get_logger(__name__)

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass(frozen=True)
class ValidationResult:
    """Result of a quality gate validation check."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    layer: str = ""


def validate_input(
    data: dict[str, Any],
    schema: dict[str, dict[str, Any]],
) -> ValidationResult:
    """Layer 1: Validate input data against a schema."""
    errors: list[str] = []

    for field_name, field_spec in schema.items():
        is_required = field_spec.get("required", False)
        expected_type_str = field_spec.get("type", "string")

        if field_name not in data:
            if is_required:
                errors.append(f"Missing required field: '{field_name}'")
            continue

        value = data[field_name]
        expected_type = _TYPE_MAP.get(expected_type_str, str)

        if not isinstance(value, expected_type):
            errors.append(
                f"Field '{field_name}' expected {expected_type_str}, "
                f"got {type(value).__name__}"
            )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        layer="input_validation",
    )


def validate_output(
    data: dict[str, Any],
    schema: dict[str, dict[str, Any]],
) -> ValidationResult:
    """Layer 2: Validate output data against expected schema."""
    if not schema:
        return ValidationResult(passed=True, layer="output_verification")

    errors: list[str] = []

    for field_name, field_spec in schema.items():
        is_required = field_spec.get("required", False)
        expected_type_str = field_spec.get("type", "string")

        if field_name not in data:
            if is_required:
                errors.append(f"Missing required output field: '{field_name}'")
            continue

        value = data[field_name]
        expected_type = _TYPE_MAP.get(expected_type_str, str)
        if not isinstance(value, expected_type):
            errors.append(
                f"Output field '{field_name}' expected {expected_type_str}, "
                f"got {type(value).__name__}"
            )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        layer="output_verification",
    )


def validate(
    data: dict[str, Any],
    schema: dict[str, dict[str, Any]],
    layer: str = "input",
) -> ValidationResult:
    """Convenience function — route to the appropriate validation layer."""
    if layer == "input":
        return validate_input(data, schema)
    elif layer == "output":
        return validate_output(data, schema)
    elif layer == "visual_qa":
        target_raw = data.get("target")
        rendered_raw = data.get("rendered")
        if not target_raw or not isinstance(target_raw, str):
            return ValidationResult(
                passed=False,
                errors=["'target' must be a non-empty string path"],
                layer="visual_qa",
            )
        if not rendered_raw or not isinstance(rendered_raw, str):
            return ValidationResult(
                passed=False,
                errors=["'rendered' must be a non-empty string path"],
                layer="visual_qa",
            )
        threshold_raw = data.get("threshold", 0.80)
        try:
            threshold_val = float(threshold_raw)
        except (TypeError, ValueError):
            return ValidationResult(
                passed=False,
                errors=[f"'threshold' must be numeric, got {threshold_raw!r}"],
                layer="visual_qa",
            )
        return validate_visual_qa(
            target=Path(target_raw),
            rendered=Path(rendered_raw),
            threshold=threshold_val,
        )
    elif layer == "content_quality":
        return validate_content_quality(
            content=str(data.get("content", "")),
            expected_languages=data.get("expected_languages"),
            expected_tone=data.get("expected_tone"),
        )
    elif layer == "delivery":
        try:
            status_val = int(data.get("status_code", 0))
        except (ValueError, TypeError) as exc:
            return ValidationResult(
                passed=False,
                errors=[f"Invalid status_code: {exc}"],
                layer="delivery",
            )
        return validate_delivery(
            status_code=status_val,
            channel=str(data.get("channel", "unknown")),
        )
    else:
        return ValidationResult(
            passed=False,
            errors=[f"Unknown validation layer: {layer}"],
            layer=layer,
        )


# ---------------------------------------------------------------------------
# Layer registry — MUST be exported (Task 27 depends on this)
# ---------------------------------------------------------------------------

LAYERS: dict[int, str] = {
    1: "input_validation",
    2: "output_verification",
    3: "visual_qa",
    4: "content_quality",
    5: "delivery_verification",
    6: "feedback_loop",
}


# ---------------------------------------------------------------------------
# Layer 3: Visual QA
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _get_language_detector() -> Any:
    """Build and cache the lingua language detector.

    Returns:
        Detector instance, or None if lingua-py is not installed.
    """
    try:
        from lingua import (  # type: ignore[import-untyped]
            Language,
            LanguageDetectorBuilder,
        )

        return LanguageDetectorBuilder.from_languages(
            Language.ENGLISH, Language.MALAY
        ).build()
    except ImportError:
        logger.warning("lingua-py not available, skipping language detection")
        return None


def _detect_language(text: str) -> str:
    """Detect language using lingua-py. Falls back to 'unknown'.

    Only detects English and Malay (the two expected client languages).
    """
    detector = _get_language_detector()
    if detector is None:
        return "unknown"

    try:
        from lingua import Language  # type: ignore[import-untyped]
    except ImportError:
        return "unknown"

    detected = detector.detect_language_of(text)
    if detected == Language.ENGLISH:
        return "en"
    if detected == Language.MALAY:
        return "ms"
    return "unknown"


def validate_visual_qa(
    *,
    target: Path,
    rendered: Path,
    threshold: float = 0.80,
) -> ValidationResult:
    """Layer 3: Visual QA -- compare rendered output against reference.

    Args:
        target: Path to the reference/expected image.
        rendered: Path to the actually rendered image.
        threshold: Minimum composite score to pass (0.0-1.0).

    Returns:
        ValidationResult indicating pass/fail with error details.
    """
    delta = calculate_delta(target=target, rendered=rendered)
    if delta.composite_score >= threshold:
        return ValidationResult(passed=True, layer="visual_qa")
    return ValidationResult(
        passed=False,
        errors=[
            f"Visual QA score {delta.composite_score:.3f} "
            f"below threshold {threshold:.3f}",
            f"SSIM: {delta.ssim_score:.3f}, "
            f"Pixel diff: {delta.pixel_diff_pct:.1f}%",
        ],
        layer="visual_qa",
    )


# ---------------------------------------------------------------------------
# Layer 4: Content quality
# ---------------------------------------------------------------------------


def validate_content_quality(
    *,
    content: str,
    expected_languages: list[str] | None = None,
    expected_tone: str | None = None,
) -> ValidationResult:
    """Layer 4: Content quality -- language detection + tone check.

    Args:
        content: The text content to validate.
        expected_languages: ISO-639-1 codes (default ``["en", "ms"]``).
        expected_tone: If ``"formal"``, checks for informal markers.

    Returns:
        ValidationResult indicating pass/fail with error details.
    """
    errors: list[str] = []
    expected_langs = expected_languages or ["en", "ms"]

    detected_lang = _detect_language(content)
    if detected_lang != "unknown" and detected_lang not in expected_langs:
        errors.append(
            f"Language mismatch: detected '{detected_lang}', "
            f"expected one of {expected_langs}"
        )

    # Basic tone check (keyword-based)
    if expected_tone == "formal":
        informal_markers = ["lol", "haha", "omg", "bruh", "ngl"]
        found = [m for m in informal_markers if m in content.lower()]
        if found:
            errors.append(f"Informal markers in formal content: {found}")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        layer="content_quality",
    )


# ---------------------------------------------------------------------------
# Layer 5: Delivery verification
# ---------------------------------------------------------------------------


def validate_delivery(
    *,
    status_code: int,
    channel: str,
) -> ValidationResult:
    """Layer 5: Delivery verification -- check HTTP response status.

    Args:
        status_code: HTTP status code from the delivery API.
        channel: Delivery channel name (e.g. ``"telegram"``, ``"whatsapp"``).

    Returns:
        ValidationResult indicating pass/fail with error details.
    """
    if 200 <= status_code < 300:
        return ValidationResult(passed=True, layer="delivery_verification")
    return ValidationResult(
        passed=False,
        errors=[f"Delivery to {channel} failed with status {status_code}"],
        layer="delivery_verification",
    )


# ---------------------------------------------------------------------------
# Layer 6: Feedback loop
# ---------------------------------------------------------------------------


def log_feedback(
    *,
    tool_name: str,
    layer: int,
    score: float,
    passed: bool,
    session_id: str,
) -> ValidationResult:
    """Layer 6: Feedback loop -- log quality data for OpenSpace.

    Args:
        tool_name: Name of the tool/pipeline that ran.
        layer: Layer number that produced the score.
        score: Quality score (0.0-1.0).
        passed: Whether the quality gate passed.
        session_id: Session identifier for traceability.

    Returns:
        ValidationResult (always passes -- logging is best-effort).
    """
    logger.info(
        "quality_gate_feedback",
        extra={
            "tool_name": tool_name,
            "layer": layer,
            "score": score,
            "pass_fail": "pass" if passed else "fail",
            "session_id": session_id,
        },
    )
    return ValidationResult(passed=True, layer="feedback_loop")
