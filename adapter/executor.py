"""Execute tools defined by YAML manifests.

Supports three execution types:
- cli: subprocess call with interpolated args
- python_script: import and call entrypoint function
- python_function: direct function call (importable)

All execution is synchronous with timeout enforcement.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

import structlog

from adapter.schemas import ManifestConfig

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_allowed_roots() -> list[Path]:
    """Return list of allowed roots for script path containment.

    Defaults to the project root. The VIZIER_ALLOWED_ROOTS env var can add
    additional trusted roots (colon-separated), used by tests with tmp dirs.
    """
    roots = [_PROJECT_ROOT]
    extra = os.environ.get("VIZIER_ALLOWED_ROOTS", "")
    if extra:
        roots.extend(Path(p).resolve() for p in extra.split(":") if p)
    return roots


def execute_tool(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Execute a tool defined by a manifest with the given arguments.

    Args:
        manifest: Validated ManifestConfig describing the tool.
        args: Input arguments to pass to the tool.

    Returns:
        JSON string with the result or an error dict.
    """
    missing = [
        name
        for name, field in manifest.input.items()
        if field.required and name not in args
    ]
    if missing:
        return json.dumps({"error": f"Missing required arguments: {missing}"})

    try:
        match manifest.execution.type:
            case "cli":
                return _execute_cli(manifest, args)
            case "python_script":
                return _execute_python_script(manifest, args)
            case "python_function":
                return _execute_python_function(manifest, args)
    except Exception as exc:
        logger.exception("Tool execution failed: %s", manifest.name)
        return json.dumps({"error": f"Execution failed: {exc}"})

    return json.dumps({"error": "Unsupported execution type"})  # pragma: no cover


def _execute_cli(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Execute a CLI command with interpolated arguments.

    Args:
        manifest: Manifest with CLI execution config.
        args: Arguments for template substitution.

    Returns:
        JSON string with stdout or error.
    """
    command_template = manifest.execution.command
    if command_template is None:
        return json.dumps({"error": "CLI manifest missing 'command'"})

    try:
        safe_args = {k: shlex.quote(str(v)) for k, v in args.items()}
        command = command_template.format(**safe_args)
    except KeyError as exc:
        return json.dumps({"error": f"Missing arg for command template: {exc}"})

    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=manifest.execution.timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"timeout after {manifest.execution.timeout}s"})

    if result.returncode != 0:
        return json.dumps(
            {
                "error": f"CLI exited with code {result.returncode}",
                "stderr": result.stderr.strip(),
            }
        )

    return json.dumps({"stdout": result.stdout.strip()})


def _execute_python_script(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Import a Python script and call its entrypoint function with timeout.

    Args:
        manifest: Manifest with python_script execution config.
        args: Arguments to pass to the entrypoint.

    Returns:
        JSON string with result or error.
    """
    script_path = manifest.execution.path
    entrypoint_name = manifest.execution.entrypoint

    if script_path is None or entrypoint_name is None:
        return json.dumps({"error": "python_script needs 'path' and 'entrypoint'"})

    allowed_roots = _get_allowed_roots()
    path = Path(script_path)
    resolved_path = path.resolve()
    if not any(resolved_path.is_relative_to(root) for root in allowed_roots):
        return json.dumps(
            {"error": f"Path escapes project root: {script_path}"}
        )
    if not path.is_file():
        return json.dumps({"error": f"Script not found: {script_path}"})

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return json.dumps({"error": f"Cannot load module from: {script_path}"})

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    entrypoint = getattr(module, entrypoint_name, None)
    if entrypoint is None:
        return json.dumps(
            {"error": f"Entrypoint '{entrypoint_name}' not found in {script_path}"}
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(entrypoint, **args)
            result = future.result(timeout=manifest.execution.timeout)
    except FuturesTimeoutError:
        return json.dumps({"error": f"timeout after {manifest.execution.timeout}s"})
    except Exception as exc:
        logger.exception("Script entrypoint raised: %s", exc)
        return json.dumps({"error": f"Execution failed: {exc}"})

    if isinstance(result, dict):
        return json.dumps(result)
    return json.dumps({"result": str(result)})


def _execute_python_function(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Import and call a Python function directly.

    Delegates to _execute_python_script since the mechanism is the same
    for on-disk importable functions.

    Args:
        manifest: Manifest with python_function execution config.
        args: Arguments to pass to the entrypoint.

    Returns:
        JSON string with result or error.
    """
    return _execute_python_script(manifest, args)
