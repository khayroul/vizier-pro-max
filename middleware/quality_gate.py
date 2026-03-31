"""Quality Gate — Layers 1-2: Input validation + Output verification.

Called explicitly by pipeline scripts and adapter/executor.py.
Not a model-callable tool — this is middleware.

Gate 1: Layers 1-2 (pydantic-based validation)
Gate 2+: Adds layers 3-6 (visual QA, content quality, delivery, feedback)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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

        if field_name not in data:
            if is_required:
                errors.append(f"Missing required output field: '{field_name}'")
            continue

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
    match layer:
        case "input":
            return validate_input(data, schema)
        case "output":
            return validate_output(data, schema)
        case _:
            return ValidationResult(
                passed=False,
                errors=[f"Unknown validation layer: {layer}"],
                layer=layer,
            )
