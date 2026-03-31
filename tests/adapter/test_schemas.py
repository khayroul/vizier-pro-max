"""Tests for manifest YAML parsing and OpenAI tool dict conversion."""
from __future__ import annotations

import pytest

from adapter.schemas import manifest_to_openai_schema, parse_manifest

VALID_MANIFEST_YAML = """
name: typst_render
description: "Compile Typst markup into PDF"
version: "1.0"
toolset: vizier-document

execution:
  type: cli
  command: "typst compile {input_path} {output_path}"
  timeout: 30

input:
  input_path:
    type: string
    required: true
    description: "Path to .typ source file"
  output_path:
    type: string
    required: true
    description: "Path for output PDF"

output:
  file_path:
    type: string
    description: "Path to generated PDF"

retry:
  max_attempts: 2
  on:
    - timeout
    - runtime_error
"""

MINIMAL_MANIFEST_YAML = """
name: simple_tool
description: "A simple tool"
version: "1.0"
toolset: vizier-core

execution:
  type: python_function
  path: scripts/content/simple.py
  entrypoint: run

input:
  text:
    type: string
    required: true

output:
  result:
    type: string
"""


class TestParseManifest:
    def test_parses_valid_manifest(self) -> None:
        config = parse_manifest(VALID_MANIFEST_YAML)
        assert config.name == "typst_render"
        assert config.toolset == "vizier-document"
        assert config.execution.type == "cli"
        assert config.execution.timeout == 30
        assert "input_path" in config.input
        assert config.input["input_path"].required is True

    def test_parses_minimal_manifest(self) -> None:
        config = parse_manifest(MINIMAL_MANIFEST_YAML)
        assert config.name == "simple_tool"
        assert config.execution.type == "python_function"
        assert config.execution.entrypoint == "run"

    def test_rejects_missing_name(self) -> None:
        bad_yaml = VALID_MANIFEST_YAML.replace("name: typst_render", "")
        with pytest.raises(ValueError):
            parse_manifest(bad_yaml)

    def test_rejects_missing_toolset(self) -> None:
        bad_yaml = VALID_MANIFEST_YAML.replace("toolset: vizier-document", "")
        with pytest.raises(ValueError):
            parse_manifest(bad_yaml)

    def test_rejects_unknown_execution_type(self) -> None:
        bad_yaml = VALID_MANIFEST_YAML.replace("type: cli", "type: docker")
        with pytest.raises(ValueError):
            parse_manifest(bad_yaml)


class TestManifestToOpenAISchema:
    def test_generates_valid_openai_schema(self) -> None:
        config = parse_manifest(VALID_MANIFEST_YAML)
        schema = manifest_to_openai_schema(config)
        assert schema["type"] == "object"
        assert "input_path" in schema["properties"]
        assert schema["properties"]["input_path"]["type"] == "string"
        assert "input_path" in schema["required"]
        assert "output_path" in schema["required"]

    def test_optional_fields_not_in_required(self) -> None:
        yaml_with_optional = """
name: test
description: "test"
version: "1.0"
toolset: vizier-core
execution:
  type: python_function
  path: test.py
  entrypoint: run
input:
  required_field:
    type: string
    required: true
  optional_field:
    type: string
    required: false
    default: "hello"
output:
  result:
    type: string
"""
        config = parse_manifest(yaml_with_optional)
        schema = manifest_to_openai_schema(config)
        assert "required_field" in schema["required"]
        assert "optional_field" not in schema["required"]
