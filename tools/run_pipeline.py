"""run_pipeline — Execute collapsed pipelines by name.

This is the Layer 1 (cheapest) tool. Pipelines are deterministic sequences
registered in pipelines/_registry.yaml and implemented as Python scripts.

Supports two modes:
- action="list": Return available pipelines and their schemas
- name="pipeline_name", args={...}: Execute a specific pipeline
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

PIPELINES_DIR = Path(__file__).parent.parent / "pipelines"


def load_pipeline_registry() -> dict[str, dict]:
    """Load the pipeline registry YAML."""
    registry_path = PIPELINES_DIR / "_registry.yaml"
    if not registry_path.is_file():
        logger.warning("Pipeline registry not found: %s", registry_path)
        return {}

    try:
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("Invalid pipeline registry YAML: %s", exc)
        return {}

    if not raw or "pipelines" not in raw:
        return {}

    return {
        entry["name"]: entry
        for entry in raw["pipelines"]
        if "name" in entry
    }


def run_pipeline(args: dict[str, Any], **kw: Any) -> str:
    """Execute a collapsed pipeline or list available pipelines."""
    action = args.get("action")

    if action == "list":
        registry = load_pipeline_registry()
        pipeline_list = [
            {"name": name, "description": meta.get("description", "")}
            for name, meta in registry.items()
        ]
        return json.dumps({"pipelines": pipeline_list})

    pipeline_name = args.get("name")
    if not pipeline_name:
        return json.dumps({"error": "Provide 'name' to execute or 'action': 'list'"})

    registry = load_pipeline_registry()
    if pipeline_name not in registry:
        available = list(registry.keys())
        return json.dumps({
            "error": f"Pipeline '{pipeline_name}' not found",
            "available": available,
            "hint": "Use action='list' for details, or use atomic tools",
        })

    script_path = PIPELINES_DIR / f"{pipeline_name}.py"

    # Prevent path traversal
    try:
        script_path.resolve().relative_to(PIPELINES_DIR.resolve())
    except ValueError:
        return json.dumps({"error": f"Invalid pipeline name: {pipeline_name}"})

    if not script_path.is_file():
        return json.dumps({"error": f"Pipeline script not found: {script_path}"})

    try:
        spec = importlib.util.spec_from_file_location(pipeline_name, script_path)
        if spec is None or spec.loader is None:
            return json.dumps({"error": f"Cannot load pipeline: {pipeline_name}"})

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        entrypoint = getattr(module, "run", None)
        if entrypoint is None:
            return json.dumps({"error": f"Pipeline '{pipeline_name}' has no run()"})

        pipeline_args = args.get("args", {})

        # Validate args against registry schema
        registry_entry = registry[pipeline_name]
        allowed_inputs = set(registry_entry.get("input", {}).keys())
        if allowed_inputs:
            unknown_keys = set(pipeline_args.keys()) - allowed_inputs
            if unknown_keys:
                return json.dumps({
                    "error": (
                        "Unknown pipeline args:"
                        f" {sorted(unknown_keys)}"
                    ),
                })

        result = entrypoint(**pipeline_args)

        if isinstance(result, dict):
            return json.dumps(result)
        return json.dumps({"result": str(result)})

    except Exception as exc:
        logger.exception("Pipeline execution failed: %s", pipeline_name)
        return json.dumps({"error": f"Pipeline failed: {exc}"})


def register_run_pipeline_tool() -> None:
    """Register run_pipeline as a Hermes tool in vizier-core toolset."""
    try:
        from tools.registry import registry  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("Hermes registry not available")
        return

    registry.register(
        name="run_pipeline",
        toolset="vizier-core",
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Set to 'list' to see available pipelines",
                    "enum": ["list"],
                },
                "name": {
                    "type": "string",
                    "description": "Pipeline name to execute",
                },
                "args": {
                    "type": "object",
                    "description": "Arguments to pass to the pipeline",
                },
            },
            "required": [],
        },
        handler=run_pipeline,
        check_fn=lambda: True,
        description="Execute collapsed pipelines or list available ones",
    )
