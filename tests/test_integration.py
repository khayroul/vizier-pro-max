"""End-to-end integration test: manifest loading -> pipeline -> quality gate."""
from __future__ import annotations

import json
from pathlib import Path

from adapter.loader import load_all_manifests
from middleware.quality_gate import validate_input, validate_output
from pipelines.content_generate import run as run_content_pipeline
from tools.run_pipeline import load_pipeline_registry, run_pipeline

MANIFESTS_DIR = Path(__file__).parent.parent / "manifests"
PIPELINES_DIR = Path(__file__).parent.parent / "pipelines"


class TestEndToEnd:
    def test_manifests_load_successfully(self) -> None:
        manifests = load_all_manifests(MANIFESTS_DIR)
        assert len(manifests) >= 4  # 4 Gate 1 manifests

    def test_pipeline_registry_loads(self) -> None:
        registry = load_pipeline_registry()
        assert "content_generate" in registry

    def test_content_pipeline_via_run_pipeline(self) -> None:
        result = json.loads(run_pipeline({
            "name": "content_generate",
            "args": {"brief": "Write a social media post about organic honey"},
        }))
        assert "content" in result
        assert "error" not in result

    def test_quality_gate_validates_pipeline_output(self) -> None:
        pipeline_result = run_content_pipeline(
            brief="Write a tagline for a halal bakery"
        )
        validation = validate_output(
            pipeline_result,
            {"content": {"type": "string", "required": True}},
        )
        assert validation.passed is True

    def test_full_flow_brief_to_validated_output(self) -> None:
        # 1. Validate input
        brief = "Create product descriptions for 3 organic tea flavors"
        input_validation = validate_input(
            {"brief": brief},
            {"brief": {"type": "string", "required": True}},
        )
        assert input_validation.passed

        # 2. Execute pipeline
        result = json.loads(run_pipeline({
            "name": "content_generate",
            "args": {"brief": brief},
        }))
        assert "error" not in result

        # 3. Validate output
        output_validation = validate_output(
            result,
            {"content": {"type": "string", "required": True}},
        )
        assert output_validation.passed
