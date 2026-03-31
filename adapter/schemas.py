"""Manifest schema definitions and YAML -> OpenAI tool dict conversion.

Pydantic models validate manifest YAML structure.
Conversion functions produce OpenAI-format tool schemas for Hermes registry.
"""
from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, field_validator


class InputField(BaseModel):
    """Schema for a single input parameter in a manifest."""

    type: str
    required: bool = True
    description: str = ""
    default: str | None = None


class OutputField(BaseModel):
    """Schema for a single output field in a manifest."""

    type: str
    description: str = ""


class RetryConfig(BaseModel):
    """Retry configuration for tool execution."""

    max_attempts: int = 1
    on: list[str] = []


class ExecutionConfig(BaseModel):
    """How to run the tool: CLI, Python script, or Python function."""

    type: Literal["cli", "python_script", "python_function"]
    command: str | None = None
    path: str | None = None
    entrypoint: str | None = None
    timeout: int = 30

    @field_validator("command")
    @classmethod
    def cli_needs_command(cls, value: str | None, info: object) -> str | None:
        """CLI execution type requires a command string."""
        return value


class ManifestConfig(BaseModel):
    """Top-level manifest configuration parsed from YAML."""

    name: str
    description: str
    version: str
    toolset: str
    execution: ExecutionConfig
    input: dict[str, InputField]
    output: dict[str, OutputField] = {}
    retry: RetryConfig = RetryConfig()

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value: str) -> str:
        """Manifest name must not be empty."""
        if not value.strip():
            raise ValueError("Manifest name must not be empty")
        return value.strip()


def parse_manifest(yaml_content: str) -> ManifestConfig:
    """Parse YAML string into a validated ManifestConfig.

    Args:
        yaml_content: Raw YAML string from a manifest file.

    Returns:
        Validated ManifestConfig instance.

    Raises:
        ValueError: If YAML is invalid or required fields are missing.
    """
    try:
        raw = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a YAML mapping")

    raw_input = raw.get("input", {})

    def _parse_input(props: object) -> InputField:
        if isinstance(props, dict):
            return InputField(**props)
        return InputField(type=str(props))

    parsed_input = {name: _parse_input(props) for name, props in raw_input.items()}
    raw["input"] = parsed_input

    raw_output = raw.get("output", {})

    def _parse_output(props: object) -> OutputField:
        if isinstance(props, dict):
            return OutputField(**props)
        return OutputField(type=str(props))

    parsed_output = {name: _parse_output(props) for name, props in raw_output.items()}
    raw["output"] = parsed_output

    try:
        return ManifestConfig(**raw)
    except Exception as exc:
        raise ValueError(f"Invalid manifest: {exc}") from exc


def manifest_to_openai_schema(config: ManifestConfig) -> dict[str, object]:
    """Convert a ManifestConfig into an OpenAI-format JSON Schema dict.

    Args:
        config: Validated ManifestConfig instance.

    Returns:
        Dictionary matching OpenAI function parameter schema format.
    """
    properties: dict[str, object] = {}
    required: list[str] = []

    for field_name, field_config in config.input.items():
        prop: dict[str, object] = {"type": field_config.type}
        if field_config.description:
            prop["description"] = field_config.description
        properties[field_name] = prop
        if field_config.required:
            required.append(field_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
