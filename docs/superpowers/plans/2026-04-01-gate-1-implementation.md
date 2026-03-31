# Vizier Pro-Max Gate 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hermes running as Vizier with one content workflow producing billable output end-to-end — manifest adapter, collapsed pipelines, quality gate, prompt logger, and bridge all operational.

**Architecture:** YAML manifests define tools. The adapter converts them into Hermes `registry.register()` calls at session init. `run_pipeline` executes collapsed pipelines. Quality gate validates every output. Bridge syncs codebase changes to Hermes memory. SOUL.md defines Vizier's persona.

**Tech Stack:** Python 3.11+, Hermes Agent v0.6.0 (`~/hermes-agent/`), pydantic, PyYAML, structlog, httpx, jinja2, lightrag, typst CLI, pytest

**Spec:** `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md`

**Hermes registry API:** `~/hermes-agent/tools/registry.py` — `registry.register(name, toolset, schema, handler, check_fn, requires_env, is_async, description, emoji)`

---

## File Map

### New files (Gate 1)

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project deps, metadata, pytest/ruff/black/pyright config |
| `CLAUDE.md` | Project-specific conventions for Claude Code |
| `adapter/__init__.py` | Package init |
| `adapter/schemas.py` | Manifest Pydantic models, YAML -> OpenAI tool dict conversion |
| `adapter/executor.py` | Run scripts/CLIs with validation, timeout, retry, error capture |
| `adapter/loader.py` | Glob manifests, parse, register into Hermes via registry.register() |
| `tools/__init__.py` | Package init |
| `tools/run_pipeline.py` | Execute or list collapsed pipelines, register as Hermes tool |
| `tools/query_logs.py` | Query prompt_log SQLite table, register as Hermes tool |
| `plugins/__init__.py` | Package init |
| `plugins/prompt_logger.py` | Hermes lifecycle hooks: pre_llm_call, post_llm_call |
| `pipelines/__init__.py` | Package init |
| `pipelines/_registry.yaml` | Pipeline index (name, description, input/output schema) |
| `pipelines/content_generate.py` | Brief -> RAG -> copy -> PDF pipeline |
| `middleware/__init__.py` | Package init |
| `middleware/quality_gate.py` | Layers 1-2: input validation + output verification |
| `manifests/content/httpx_fetch.yaml` | Manifest for httpx URL fetching |
| `manifests/content/jinja2_render.yaml` | Manifest for Jinja2 template rendering |
| `manifests/content/lightrag_search.yaml` | Manifest for LightRAG retrieval |
| `manifests/document/typst_render.yaml` | Manifest for Typst PDF rendering |
| `bridge/__init__.py` | Package init |
| `bridge/git_watcher.py` | Cherry-picked + adapted from vizier-ultimate |
| `bridge/skill_syncer.py` | Cherry-picked from vizier-ultimate |
| `bridge/test_parser.py` | Cherry-picked from vizier-ultimate |
| `bridge/manifest_syncer.py` | NEW: watch manifests/, update registry |
| `bridge/watcher.py` | Entry point for all bridge components |
| `config/SOUL.md` | Vizier persona + tool-layer priority rules |
| `config/hermes.yaml` | Hermes runtime config |
| `scripts/content/fetch_url.py` | httpx wrapper script |
| `scripts/content/render_template.py` | Jinja2 wrapper script |
| `scripts/content/search_rag.py` | LightRAG wrapper script |
| `scripts/document/render_typst.py` | Typst CLI wrapper script |

### Test files

| Test file | Tests for |
|-----------|-----------|
| `tests/adapter/test_schemas.py` | Manifest parsing, YAML -> OpenAI dict |
| `tests/adapter/test_executor.py` | Script/CLI execution, timeout, retry |
| `tests/adapter/test_loader.py` | Manifest globbing, Hermes registration |
| `tests/tools/test_run_pipeline.py` | Pipeline execution, list mode, error handling |
| `tests/tools/test_query_logs.py` | Log querying, filtering |
| `tests/plugins/test_prompt_logger.py` | Hook capture, SQLite writes |
| `tests/middleware/test_quality_gate.py` | Input/output validation |
| `tests/pipelines/test_content_generate.py` | End-to-end content pipeline |
| `tests/bridge/test_git_watcher.py` | Cherry-picked + adapted |
| `tests/bridge/test_skill_syncer.py` | Cherry-picked |
| `tests/bridge/test_test_parser.py` | Cherry-picked |
| `tests/bridge/test_manifest_syncer.py` | New manifest detection, validation |
| `tests/bridge/test_watcher.py` | Entry point orchestration |

---

## Chunk 1: Project Scaffold + Adapter

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `CLAUDE.md`
- Create: `adapter/__init__.py`, `tools/__init__.py`, `plugins/__init__.py`, `pipelines/__init__.py`, `middleware/__init__.py`, `bridge/__init__.py`
- Create: `tests/__init__.py`, `tests/adapter/__init__.py`, `tests/tools/__init__.py`, `tests/plugins/__init__.py`, `tests/middleware/__init__.py`, `tests/pipelines/__init__.py`, `tests/bridge/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "vizier-pro-max"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "structlog>=24.0",
    "httpx>=0.27",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pyright>=1.1",
    "ruff>=0.4",
    "black>=24.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.black]
line-length = 88
target-version = ["py311"]

[tool.pyright]
pythonVersion = "3.11"
typeCheckingMode = "standard"
```

- [ ] **Step 2: Create CLAUDE.md**

```markdown
# Vizier Pro-Max

Global rules (Python, immutability, testing, git, security, halal) apply.

## Architecture
- **Spec:** `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md`
- **Plan:** `docs/superpowers/plans/2026-04-01-gate-1-implementation.md`
- **Foundation:** Hermes Agent v0.6.0 at ~/hermes-agent/
- **Model:** GPT-5.4-mini (free 10M/day) via Hermes
- **Registry API:** ~/hermes-agent/tools/registry.py

## Conventions
- Manifests in `manifests/{workflow}/` — YAML, one per tool
- Scripts in `scripts/{workflow}/` — stable Python executables
- Pipelines in `pipelines/` — collapsed deterministic sequences
- Bridge in `bridge/` — Claude Code <-> Vizier awareness
- Custom Hermes tools in `tools/` — registered via registry.register()
- Hermes lifecycle hooks in `plugins/` — NOT tools
- Test files mirror source: `adapter/loader.py` -> `tests/adapter/test_loader.py`

## No litellm. Ever.
Supply chain compromise confirmed. Use direct provider SDKs via Hermes.
```

- [ ] **Step 3: Create all __init__.py files**

All `__init__.py` files are empty except for the top-level packages:

```python
# adapter/__init__.py
"""Universal manifest -> Hermes tool adapter."""
```

```python
# tools/__init__.py
"""Custom Hermes tool handlers."""
```

```python
# plugins/__init__.py
"""Hermes lifecycle hook plugins."""
```

```python
# pipelines/__init__.py
"""Collapsed pipeline scripts."""
```

```python
# middleware/__init__.py
"""Cross-cutting middleware (quality gate, etc.)."""
```

```python
# bridge/__init__.py
"""Bidirectional Claude Code <-> Vizier awareness."""
```

All test `__init__.py` files are empty.

- [ ] **Step 4: Create directory structure for manifests, scripts, config**

```bash
mkdir -p manifests/content manifests/document
mkdir -p scripts/content scripts/document
mkdir -p config/clients
mkdir -p pipelines/_drafts
mkdir -p output tmp
```

- [ ] **Step 5: Install dev dependencies and verify**

```bash
cd ~/vizier-pro-max
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest --version
pyright --version
```

- [ ] **Step 6: Commit scaffold**

```bash
git add -A
git commit -m "chore: project scaffold with package structure and tooling config"
```

---

### Task 2: Manifest schemas (adapter/schemas.py)

**Files:**
- Create: `adapter/schemas.py`
- Create: `tests/adapter/test_schemas.py`

- [ ] **Step 1: Write failing tests for manifest parsing**

```python
# tests/adapter/test_schemas.py
"""Tests for manifest YAML parsing and OpenAI tool dict conversion."""
from __future__ import annotations

import pytest

from adapter.schemas import ManifestConfig, manifest_to_openai_schema, parse_manifest


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/vizier-pro-max
pytest tests/adapter/test_schemas.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'adapter.schemas'`

- [ ] **Step 3: Implement adapter/schemas.py**

```python
# adapter/schemas.py
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
        ValueError: If YAML is invalid or missing required fields.
    """
    try:
        raw = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a YAML mapping")

    # Convert input/output dicts of dicts into dicts of typed models
    raw_input = raw.get("input", {})
    parsed_input = {
        name: InputField(**props) if isinstance(props, dict) else InputField(type=str(props))
        for name, props in raw_input.items()
    }
    raw["input"] = parsed_input

    raw_output = raw.get("output", {})
    parsed_output = {
        name: OutputField(**props) if isinstance(props, dict) else OutputField(type=str(props))
        for name, props in raw_output.items()
    }
    raw["output"] = parsed_output

    return ManifestConfig(**raw)


def manifest_to_openai_schema(config: ManifestConfig) -> dict:
    """Convert a ManifestConfig into an OpenAI-format JSON Schema dict.

    This schema is passed to Hermes registry.register() as the ``schema``
    parameter. It defines what arguments the LLM can pass to this tool.

    Args:
        config: Validated manifest configuration.

    Returns:
        OpenAI-format tool parameters schema dict.
    """
    properties: dict = {}
    required: list[str] = []

    for field_name, field_config in config.input.items():
        prop: dict = {"type": field_config.type}
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapter/test_schemas.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Run pyright and ruff**

```bash
pyright adapter/schemas.py
ruff check adapter/schemas.py
black --check adapter/schemas.py
```

- [ ] **Step 6: Commit**

```bash
git add adapter/schemas.py tests/adapter/test_schemas.py
git commit -m "feat: manifest schema parsing with YAML -> OpenAI tool dict conversion"
```

---

### Task 3: Tool executor (adapter/executor.py)

**Files:**
- Create: `adapter/executor.py`
- Create: `tests/adapter/test_executor.py`

- [ ] **Step 1: Write failing tests for executor**

```python
# tests/adapter/test_executor.py
"""Tests for tool execution: CLI, Python script, Python function."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from adapter.executor import execute_tool
from adapter.schemas import ManifestConfig, parse_manifest


@pytest.fixture()
def tmp_script(tmp_path: Path) -> Path:
    """Create a temporary Python script that echoes input as JSON."""
    script = tmp_path / "echo_tool.py"
    script.write_text(textwrap.dedent("""
        import json
        import sys

        def run(text: str) -> dict:
            return {"echoed": text, "length": len(text)}

        if __name__ == "__main__":
            args = json.loads(sys.argv[1])
            result = run(**args)
            print(json.dumps(result))
    """))
    return script


@pytest.fixture()
def script_manifest(tmp_script: Path) -> ManifestConfig:
    """Manifest pointing at the temp echo script."""
    yaml_str = f"""
name: echo_tool
description: "Echo input text"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: "{tmp_script}"
  entrypoint: run
  timeout: 10
input:
  text:
    type: string
    required: true
output:
  echoed:
    type: string
  length:
    type: integer
"""
    return parse_manifest(yaml_str)


class TestExecuteTool:
    def test_executes_python_script(self, script_manifest: ManifestConfig) -> None:
        result = execute_tool(script_manifest, {"text": "hello"})
        parsed = json.loads(result)
        assert parsed["echoed"] == "hello"
        assert parsed["length"] == 5

    def test_returns_error_on_missing_required_arg(
        self, script_manifest: ManifestConfig
    ) -> None:
        result = execute_tool(script_manifest, {})
        parsed = json.loads(result)
        assert "error" in parsed

    def test_returns_error_on_timeout(self, tmp_path: Path) -> None:
        slow_script = tmp_path / "slow.py"
        slow_script.write_text(textwrap.dedent("""
            import time
            def run():
                time.sleep(60)
                return {"done": True}
        """))
        yaml_str = f"""
name: slow_tool
description: "Slow tool"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: "{slow_script}"
  entrypoint: run
  timeout: 1
input: {{}}
output:
  done:
    type: boolean
"""
        config = parse_manifest(yaml_str)
        result = execute_tool(config, {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "timeout" in parsed["error"].lower()

    def test_executes_cli_command(self, tmp_path: Path) -> None:
        yaml_str = """
name: echo_cli
description: "Echo via CLI"
version: "1.0"
toolset: vizier-core
execution:
  type: cli
  command: "echo {text}"
  timeout: 5
input:
  text:
    type: string
    required: true
output:
  stdout:
    type: string
"""
        config = parse_manifest(yaml_str)
        result = execute_tool(config, {"text": "hello_world"})
        parsed = json.loads(result)
        assert "hello_world" in parsed.get("stdout", "")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/adapter/test_executor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'adapter.executor'`

- [ ] **Step 3: Implement adapter/executor.py**

```python
# adapter/executor.py
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
import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from adapter.schemas import ManifestConfig

logger = logging.getLogger(__name__)


def execute_tool(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Execute a tool defined by a manifest with the given arguments.

    Args:
        manifest: Parsed manifest configuration.
        args: Arguments from the LLM tool call.

    Returns:
        JSON string with the result or error dict.
    """
    # Validate required args
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
    except TimeoutError:
        return json.dumps({"error": f"Timeout after {manifest.execution.timeout}s"})
    except Exception as exc:
        logger.exception("Tool execution failed: %s", manifest.name)
        return json.dumps({"error": f"Execution failed: {exc}"})


def _execute_cli(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Execute a CLI command with interpolated arguments."""
    command_template = manifest.execution.command
    if command_template is None:
        return json.dumps({"error": "CLI manifest missing 'command'"})

    # Interpolate args into command template
    try:
        command = command_template.format(**args)
    except KeyError as exc:
        return json.dumps({"error": f"Missing arg for command template: {exc}"})

    result = subprocess.run(
        shlex.split(command),
        capture_output=True,
        text=True,
        timeout=manifest.execution.timeout,
    )

    if result.returncode != 0:
        return json.dumps({
            "error": f"CLI exited with code {result.returncode}",
            "stderr": result.stderr.strip(),
        })

    return json.dumps({"stdout": result.stdout.strip()})


def _execute_python_script(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Import a Python script and call its entrypoint function."""
    script_path = manifest.execution.path
    entrypoint_name = manifest.execution.entrypoint

    if script_path is None or entrypoint_name is None:
        return json.dumps({"error": "python_script needs 'path' and 'entrypoint'"})

    path = Path(script_path)
    if not path.is_file():
        return json.dumps({"error": f"Script not found: {script_path}"})

    # Dynamic import
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return json.dumps({"error": f"Cannot load module from: {script_path}"})

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    entrypoint = getattr(module, entrypoint_name, None)
    if entrypoint is None:
        return json.dumps(
            {"error": f"Entrypoint '{entrypoint_name}' not found in {script_path}"}
        )

    result = entrypoint(**args)

    if isinstance(result, dict):
        return json.dumps(result)
    return json.dumps({"result": str(result)})


def _execute_python_function(manifest: ManifestConfig, args: dict[str, Any]) -> str:
    """Import and call a Python function directly."""
    # Same as python_script — the distinction is semantic (script = standalone,
    # function = part of a larger module). Implementation is identical.
    return _execute_python_script(manifest, args)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapter/test_executor.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Run pyright and ruff**

```bash
pyright adapter/executor.py
ruff check adapter/executor.py
```

- [ ] **Step 6: Commit**

```bash
git add adapter/executor.py tests/adapter/test_executor.py
git commit -m "feat: tool executor with CLI, python_script, and timeout handling"
```

---

### Task 4: Manifest loader (adapter/loader.py)

**Files:**
- Create: `adapter/loader.py`
- Create: `tests/adapter/test_loader.py`

- [ ] **Step 1: Write failing tests for loader**

```python
# tests/adapter/test_loader.py
"""Tests for manifest globbing and Hermes tool registration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adapter.loader import load_all_manifests, register_manifest


@pytest.fixture()
def manifest_dir(tmp_path: Path) -> Path:
    """Create a temporary manifests directory with YAML files."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "httpx_fetch.yaml").write_text("""
name: httpx_fetch
description: "Fetch a URL"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: scripts/content/fetch_url.py
  entrypoint: fetch
  timeout: 15
input:
  url:
    type: string
    required: true
    description: "URL to fetch"
output:
  body:
    type: string
""")
    return tmp_path


class TestLoadAllManifests:
    def test_discovers_yaml_files(self, manifest_dir: Path) -> None:
        manifests = load_all_manifests(manifest_dir)
        assert len(manifests) == 1
        assert manifests[0].name == "httpx_fetch"

    def test_skips_invalid_yaml(self, manifest_dir: Path) -> None:
        bad_file = manifest_dir / "content" / "broken.yaml"
        bad_file.write_text("not: valid: yaml: [[[")
        manifests = load_all_manifests(manifest_dir)
        # Should still load the valid one, skip the broken one
        assert len(manifests) == 1

    def test_returns_empty_for_missing_dir(self, tmp_path: Path) -> None:
        manifests = load_all_manifests(tmp_path / "nonexistent")
        assert manifests == []


class TestRegisterManifest:
    @patch("adapter.loader._get_registry")
    def test_calls_registry_register(self, mock_get_registry: MagicMock, manifest_dir: Path) -> None:
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        manifests = load_all_manifests(manifest_dir)
        register_manifest(manifests[0])

        mock_registry.register.assert_called_once()
        call_kwargs = mock_registry.register.call_args
        assert call_kwargs[1]["name"] == "httpx_fetch"
        assert call_kwargs[1]["toolset"] == "vizier-core"
        assert "url" in call_kwargs[1]["schema"]["properties"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/adapter/test_loader.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement adapter/loader.py**

```python
# adapter/loader.py
"""Load YAML manifests and register tools into Hermes via registry.register().

This module is imported during Hermes session init. It globs all YAML files
under the manifests directory, parses them, and registers each as a Hermes tool
in the appropriate toolset.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from adapter.executor import execute_tool
from adapter.schemas import ManifestConfig, manifest_to_openai_schema, parse_manifest

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _get_registry():  # type: ignore[no-untyped-def]
    """Lazy import of Hermes tool registry to avoid circular imports.

    Returns the singleton registry instance from Hermes.
    Falls back to a mock-like object if Hermes is not available (testing).
    """
    try:
        from tools.registry import registry  # type: ignore[import-not-found]

        return registry
    except ImportError:
        logger.warning("Hermes registry not available — tools will not be registered")
        return None


def load_all_manifests(manifests_dir: Path) -> list[ManifestConfig]:
    """Glob all YAML manifests under the given directory.

    Args:
        manifests_dir: Root directory containing workflow subdirectories
            with YAML manifest files.

    Returns:
        List of parsed ManifestConfig objects. Invalid files are logged
        and skipped.
    """
    if not manifests_dir.is_dir():
        logger.warning("Manifests directory not found: %s", manifests_dir)
        return []

    manifests: list[ManifestConfig] = []

    for yaml_path in sorted(manifests_dir.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue  # Skip _registry.yaml and other internal files

        try:
            content = yaml_path.read_text(encoding="utf-8")
            config = parse_manifest(content)
            manifests.append(config)
            logger.info("Loaded manifest: %s (toolset: %s)", config.name, config.toolset)
        except (ValueError, OSError) as exc:
            logger.warning("Skipping invalid manifest %s: %s", yaml_path, exc)

    return manifests


def register_manifest(manifest: ManifestConfig) -> None:
    """Register a single manifest as a Hermes tool.

    Converts the manifest to an OpenAI-format schema and calls
    tools.registry.register() with the appropriate toolset.

    Args:
        manifest: Parsed and validated manifest configuration.
    """
    registry = _get_registry()
    if registry is None:
        return

    schema = manifest_to_openai_schema(manifest)

    registry.register(
        name=manifest.name,
        toolset=manifest.toolset,
        schema=schema,
        handler=lambda args, **kw: execute_tool(manifest, args),
        check_fn=lambda: True,
        description=manifest.description,
    )

    logger.info("Registered tool: %s -> toolset %s", manifest.name, manifest.toolset)


def register_all(manifests_dir: Path) -> int:
    """Load all manifests and register them into Hermes.

    Args:
        manifests_dir: Root directory containing manifest YAML files.

    Returns:
        Number of tools successfully registered.
    """
    manifests = load_all_manifests(manifests_dir)
    registered = 0

    for manifest in manifests:
        try:
            register_manifest(manifest)
            registered += 1
        except Exception as exc:
            logger.warning("Failed to register %s: %s", manifest.name, exc)

    logger.info("Registered %d/%d tools from manifests", registered, len(manifests))
    return registered
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapter/test_loader.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Run pyright and ruff**

```bash
pyright adapter/loader.py
ruff check adapter/loader.py
```

- [ ] **Step 6: Commit**

```bash
git add adapter/loader.py tests/adapter/test_loader.py
git commit -m "feat: manifest loader with Hermes registry.register() integration"
```

---

## Chunk 2: Tools + Plugins + Pipelines + Middleware

### Task 5: Prompt logger plugin (plugins/prompt_logger.py)

**Files:**
- Create: `plugins/prompt_logger.py`
- Create: `tests/plugins/test_prompt_logger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/plugins/test_prompt_logger.py
"""Tests for prompt logger lifecycle hooks."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plugins.prompt_logger import post_llm_call, pre_llm_call, _ensure_table


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary SQLite database path."""
    return tmp_path / "test_state.db"


@pytest.fixture(autouse=True)
def _patch_db(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch DB_PATH to use temp database."""
    monkeypatch.setattr("plugins.prompt_logger.DB_PATH", str(db_path))
    _ensure_table(str(db_path))


class TestPreLLMCall:
    def test_inserts_log_entry(self, db_path: Path) -> None:
        messages = [{"role": "user", "content": "hello"}]
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-1")

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM prompt_log").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_increments_step_counter(self, db_path: Path) -> None:
        messages = [{"role": "user", "content": "hello"}]
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-1")
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-1")

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT step FROM prompt_log WHERE task_id = 'task-1' ORDER BY step"
        ).fetchall()
        conn.close()
        assert [r[0] for r in rows] == [1, 2]


class TestPostLLMCall:
    def test_updates_token_counts(self, db_path: Path) -> None:
        messages = [{"role": "user", "content": "hello"}]
        pre_llm_call(messages=messages, model="gpt-5.4-mini", task_id="task-2")
        post_llm_call(
            response=None,
            task_id="task-2",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT tokens_in, tokens_out FROM prompt_log WHERE task_id = 'task-2'"
        ).fetchone()
        conn.close()
        assert row == (100, 50)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/plugins/test_prompt_logger.py -v
```

- [ ] **Step 3: Implement plugins/prompt_logger.py**

Cherry-pick from v6.2 architecture Section 27 with minor adaptations:

```python
# plugins/prompt_logger.py
"""Prompt Logger — Hermes lifecycle hook plugin.

Captures the full prompt chain for every LLM call into SQLite.
This is a lifecycle hook (pre_llm_call / post_llm_call), NOT a tool.
The query_logs tool in tools/ provides model-accessible inspection.

Install: symlink or copy to ~/.hermes/plugins/prompt_logger/
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")
_step_counter: dict[str, int] = {}


def _ensure_table(db_path: str | None = None) -> None:
    """Create the prompt_log table if it does not exist.

    Args:
        db_path: Override database path (for testing). Uses DB_PATH if None.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            step INTEGER,
            model TEXT,
            messages_json TEXT,
            tools_json TEXT,
            timestamp REAL,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


_ensure_table()


def pre_llm_call(
    messages: list[dict],
    model: str,
    tools: list[dict] | None = None,
    task_id: str | None = None,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook — fires before every LLM call.

    Args:
        messages: Conversation messages being sent.
        model: Model name.
        tools: Tool definitions (if any).
        task_id: Current task identifier.
    """
    effective_task_id = task_id or "unknown"
    _step_counter[effective_task_id] = _step_counter.get(effective_task_id, 0) + 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO prompt_log
           (task_id, step, model, messages_json, tools_json, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            effective_task_id,
            _step_counter[effective_task_id],
            model or "unknown",
            json.dumps(messages, ensure_ascii=False, default=str),
            json.dumps(tools, ensure_ascii=False, default=str) if tools else "[]",
            time.time(),
        ],
    )
    conn.commit()
    conn.close()


def post_llm_call(
    response: object = None,
    task_id: str | None = None,
    usage: dict[str, int] | None = None,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook — fires after every LLM call. Updates token counts.

    Args:
        response: Model response (unused, logged elsewhere).
        task_id: Current task identifier.
        usage: Token usage dict with prompt_tokens and completion_tokens.
    """
    if task_id is None or usage is None:
        return

    step = _step_counter.get(task_id, 0)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """UPDATE prompt_log SET tokens_in = ?, tokens_out = ?
           WHERE task_id = ? AND step = ?""",
        [
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            task_id,
            step,
        ],
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/plugins/test_prompt_logger.py -v
```

- [ ] **Step 5: Run pyright, ruff, commit**

```bash
pyright plugins/prompt_logger.py
ruff check plugins/prompt_logger.py
git add plugins/prompt_logger.py tests/plugins/test_prompt_logger.py
git commit -m "feat: prompt logger lifecycle hook plugin with SQLite capture"
```

---

### Task 6: Query logs tool (tools/query_logs.py)

**Files:**
- Create: `tools/query_logs.py`
- Create: `tests/tools/test_query_logs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tools/test_query_logs.py
"""Tests for query_logs Hermes tool."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tools.query_logs import query_logs


@pytest.fixture()
def db_with_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp database with sample prompt log entries."""
    db_path = tmp_path / "test_state.db"
    monkeypatch.setattr("tools.query_logs.DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY, task_id TEXT, step INTEGER,
            model TEXT, messages_json TEXT, tools_json TEXT,
            timestamp REAL, tokens_in INTEGER, tokens_out INTEGER
        )
    """)
    conn.executemany(
        "INSERT INTO prompt_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "task-1", 1, "gpt-5.4-mini", "[]", "[]", 1000.0, 100, 50),
            (2, "task-1", 2, "gpt-5.4-mini", "[]", "[]", 1001.0, 200, 80),
            (3, "task-2", 1, "gpt-5.4-mini", "[]", "[]", 1002.0, 150, 60),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


class TestQueryLogs:
    def test_returns_last_n_entries(self, db_with_logs: Path) -> None:
        result = json.loads(query_logs({"last_n": 2}))
        assert len(result["entries"]) == 2

    def test_filters_by_task_id(self, db_with_logs: Path) -> None:
        result = json.loads(query_logs({"task_id": "task-1"}))
        assert len(result["entries"]) == 2
        assert all(e["task_id"] == "task-1" for e in result["entries"])

    def test_returns_token_summary(self, db_with_logs: Path) -> None:
        result = json.loads(query_logs({"task_id": "task-1", "summary": True}))
        assert result["total_tokens_in"] == 300
        assert result["total_tokens_out"] == 130
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_query_logs.py -v
```

- [ ] **Step 3: Implement tools/query_logs.py**

```python
# tools/query_logs.py
"""Query prompt logger traces — model-callable Hermes tool.

Provides inspection of the prompt_log SQLite table populated by
the prompt_logger lifecycle hook in plugins/.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")


def query_logs(args: dict[str, Any], **kw: Any) -> str:
    """Query prompt log entries.

    Args (from LLM tool call):
        last_n: Return the last N entries (default 10).
        task_id: Filter by specific task ID.
        summary: If true, return token totals instead of entries.

    Returns:
        JSON string with entries or summary.
    """
    last_n = args.get("last_n", 10)
    task_id = args.get("task_id")
    summary = args.get("summary", False)

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if summary and task_id:
            row = conn.execute(
                """SELECT SUM(tokens_in) as total_in, SUM(tokens_out) as total_out,
                          COUNT(*) as call_count
                   FROM prompt_log WHERE task_id = ?""",
                [task_id],
            ).fetchone()
            conn.close()
            return json.dumps({
                "task_id": task_id,
                "total_tokens_in": row["total_in"] or 0,
                "total_tokens_out": row["total_out"] or 0,
                "call_count": row["call_count"],
            })

        if task_id:
            rows = conn.execute(
                """SELECT task_id, step, model, tokens_in, tokens_out, timestamp
                   FROM prompt_log WHERE task_id = ? ORDER BY step""",
                [task_id],
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT task_id, step, model, tokens_in, tokens_out, timestamp
                   FROM prompt_log ORDER BY id DESC LIMIT ?""",
                [last_n],
            ).fetchall()

        conn.close()
        entries = [dict(row) for row in rows]
        return json.dumps({"entries": entries})

    except sqlite3.OperationalError as exc:
        return json.dumps({"error": f"Database error: {exc}"})


def register_query_logs_tool() -> None:
    """Register query_logs as a Hermes tool in the vizier-core toolset.

    Call this during Hermes session init alongside manifest registration.
    """
    try:
        from tools.registry import registry  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("Hermes registry not available — query_logs not registered")
        return

    registry.register(
        name="query_logs",
        toolset="vizier-core",
        schema={
            "type": "object",
            "properties": {
                "last_n": {
                    "type": "integer",
                    "description": "Return the last N log entries (default 10)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Filter by specific task ID",
                },
                "summary": {
                    "type": "boolean",
                    "description": "Return token totals instead of entries",
                },
            },
            "required": [],
        },
        handler=query_logs,
        check_fn=lambda: True,
        description="Inspect prompt logger traces: view LLM call chains, token usage per task",
    )
```

- [ ] **Step 4: Run tests, pyright, ruff, commit**

```bash
pytest tests/tools/test_query_logs.py -v
pyright tools/query_logs.py
ruff check tools/query_logs.py
git add tools/query_logs.py tests/tools/test_query_logs.py
git commit -m "feat: query_logs tool for inspecting prompt logger traces"
```

---

### Task 7: run_pipeline tool (tools/run_pipeline.py)

**Files:**
- Create: `tools/run_pipeline.py`
- Create: `tests/tools/test_run_pipeline.py`
- Create: `pipelines/_registry.yaml`

- [ ] **Step 1: Write failing tests**

```python
# tests/tools/test_run_pipeline.py
"""Tests for run_pipeline Hermes tool."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tools.run_pipeline import run_pipeline, load_pipeline_registry


@pytest.fixture()
def pipeline_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create temp pipeline directory with registry and a sample pipeline."""
    monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)

    # Registry
    (tmp_path / "_registry.yaml").write_text("""
pipelines:
  - name: test_pipeline
    description: "A test pipeline"
    input:
      text:
        type: string
        required: true
    output:
      result:
        type: string
""")

    # Pipeline script
    (tmp_path / "test_pipeline.py").write_text(textwrap.dedent("""
        def run(text: str) -> dict:
            return {"result": f"processed: {text}"}
    """))

    return tmp_path


class TestLoadPipelineRegistry:
    def test_loads_valid_registry(self, pipeline_dir: Path) -> None:
        registry = load_pipeline_registry()
        assert "test_pipeline" in registry
        assert registry["test_pipeline"]["description"] == "A test pipeline"

    def test_returns_empty_for_missing_registry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path / "nope")
        registry = load_pipeline_registry()
        assert registry == {}


class TestRunPipeline:
    def test_executes_pipeline(self, pipeline_dir: Path) -> None:
        result = json.loads(run_pipeline({"name": "test_pipeline", "args": {"text": "hello"}}))
        assert result["result"] == "processed: hello"

    def test_returns_error_for_unknown_pipeline(self, pipeline_dir: Path) -> None:
        result = json.loads(run_pipeline({"name": "nonexistent"}))
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_list_mode_returns_registry(self, pipeline_dir: Path) -> None:
        result = json.loads(run_pipeline({"action": "list"}))
        assert "pipelines" in result
        assert len(result["pipelines"]) == 1
        assert result["pipelines"][0]["name"] == "test_pipeline"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_run_pipeline.py -v
```

- [ ] **Step 3: Implement tools/run_pipeline.py**

```python
# tools/run_pipeline.py
"""run_pipeline — Execute collapsed pipelines by name.

This is the Layer 1 (cheapest) tool. Pipelines are deterministic sequences
registered in pipelines/_registry.yaml and implemented as Python scripts
in the pipelines/ directory.

Supports two modes:
- action="list": Return available pipelines and their schemas
- name="pipeline_name", args={...}: Execute a specific pipeline
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PIPELINES_DIR = Path(__file__).parent.parent / "pipelines"


def load_pipeline_registry() -> dict[str, dict]:
    """Load the pipeline registry YAML.

    Returns:
        Dict mapping pipeline names to their metadata (description, input, output).
    """
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
    """Execute a collapsed pipeline or list available pipelines.

    Args (from LLM tool call):
        action: "list" to return available pipelines.
        name: Pipeline name to execute.
        args: Arguments to pass to the pipeline's run() function.

    Returns:
        JSON string with pipeline result or error.
    """
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
        return json.dumps({"error": "Provide 'name' to execute a pipeline or 'action': 'list'"})

    registry = load_pipeline_registry()
    if pipeline_name not in registry:
        available = list(registry.keys())
        return json.dumps({
            "error": f"Pipeline '{pipeline_name}' not found",
            "available": available,
            "hint": "Use action='list' for details, or use atomic tools",
        })

    # Load and execute the pipeline script
    script_path = PIPELINES_DIR / f"{pipeline_name}.py"
    if not script_path.is_file():
        return json.dumps({"error": f"Pipeline script not found: {script_path}"})

    try:
        spec = importlib.util.spec_from_file_location(pipeline_name, script_path)
        if spec is None or spec.loader is None:
            return json.dumps({"error": f"Cannot load pipeline: {pipeline_name}"})

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        entrypoint = getattr(module, "run", None)
        if entrypoint is None:
            return json.dumps({"error": f"Pipeline '{pipeline_name}' has no run() function"})

        pipeline_args = args.get("args", {})
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
        logger.warning("Hermes registry not available — run_pipeline not registered")
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
        description="Execute collapsed pipelines (cheapest) or list available ones",
    )
```

- [ ] **Step 4: Create pipelines/_registry.yaml**

```yaml
# pipelines/_registry.yaml
# Pipeline index — consumed by tools/run_pipeline.py
# Each pipeline has a corresponding .py file in this directory with a run() function.

pipelines:
  - name: content_generate
    description: "Brief -> RAG retrieval -> content generation -> PDF render -> delivery-ready"
    input:
      brief:
        type: string
        required: true
        description: "Content brief describing what to produce"
      client_id:
        type: string
        required: false
        description: "Client ID for brand context (loads from config/clients/)"
      output_format:
        type: string
        required: false
        description: "Output format: 'pdf', 'markdown', 'html' (default: markdown)"
    output:
      content:
        type: string
        description: "Generated content"
      pdf_path:
        type: string
        description: "Path to rendered PDF (if output_format=pdf)"
```

- [ ] **Step 5: Run tests, pyright, ruff, commit**

```bash
pytest tests/tools/test_run_pipeline.py -v
pyright tools/run_pipeline.py
ruff check tools/run_pipeline.py
git add tools/run_pipeline.py tests/tools/test_run_pipeline.py pipelines/_registry.yaml
git commit -m "feat: run_pipeline tool with registry loading and list mode"
```

---

### Task 8: Quality gate middleware (middleware/quality_gate.py)

**Files:**
- Create: `middleware/quality_gate.py`
- Create: `tests/middleware/test_quality_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/middleware/test_quality_gate.py
"""Tests for quality gate middleware layers 1-2."""
from __future__ import annotations

import pytest

from middleware.quality_gate import validate_input, validate_output, ValidationResult


class TestValidateInput:
    def test_passes_valid_input(self) -> None:
        schema = {"brief": {"type": "string", "required": True}}
        result = validate_input({"brief": "Write an ad for DMB"}, schema)
        assert result.passed is True

    def test_fails_missing_required_field(self) -> None:
        schema = {"brief": {"type": "string", "required": True}}
        result = validate_input({}, schema)
        assert result.passed is False
        assert "brief" in result.errors[0]

    def test_fails_wrong_type(self) -> None:
        schema = {"count": {"type": "integer", "required": True}}
        result = validate_input({"count": "not_a_number"}, schema)
        assert result.passed is False


class TestValidateOutput:
    def test_passes_valid_output(self) -> None:
        schema = {"content": {"type": "string"}}
        result = validate_output({"content": "Hello world"}, schema)
        assert result.passed is True

    def test_fails_empty_required_output(self) -> None:
        schema = {"content": {"type": "string", "required": True}}
        result = validate_output({}, schema)
        assert result.passed is False

    def test_passes_empty_schema(self) -> None:
        result = validate_output({"anything": "goes"}, {})
        assert result.passed is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/middleware/test_quality_gate.py -v
```

- [ ] **Step 3: Implement middleware/quality_gate.py**

```python
# middleware/quality_gate.py
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
    """Result of a quality gate validation check.

    Attributes:
        passed: Whether validation succeeded.
        errors: List of error messages (empty if passed).
        layer: Which QA layer produced this result.
    """

    passed: bool
    errors: list[str] = field(default_factory=list)
    layer: str = ""


def validate_input(
    data: dict[str, Any],
    schema: dict[str, dict[str, Any]],
) -> ValidationResult:
    """Layer 1: Validate input data against a schema.

    Args:
        data: Input dict from LLM or user.
        schema: Field definitions with type and required flags.

    Returns:
        ValidationResult with pass/fail and error messages.
    """
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
    """Layer 2: Validate output data against expected schema.

    Args:
        data: Output dict from tool execution or pipeline.
        schema: Expected output field definitions.

    Returns:
        ValidationResult with pass/fail and error messages.
    """
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
    """Convenience function — route to the appropriate validation layer.

    Args:
        data: Data to validate.
        schema: Field definitions.
        layer: "input" or "output".

    Returns:
        ValidationResult.
    """
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
```

- [ ] **Step 4: Run tests, pyright, ruff, commit**

```bash
pytest tests/middleware/test_quality_gate.py -v
pyright middleware/quality_gate.py
ruff check middleware/quality_gate.py
git add middleware/quality_gate.py tests/middleware/test_quality_gate.py
git commit -m "feat: quality gate layers 1-2 (input/output validation)"
```

---

### Task 9: Content generate pipeline (pipelines/content_generate.py)

**Files:**
- Create: `pipelines/content_generate.py`
- Create: `tests/pipelines/test_content_generate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipelines/test_content_generate.py
"""Tests for content_generate pipeline."""
from __future__ import annotations

import json

import pytest

from pipelines.content_generate import run


class TestContentGeneratePipeline:
    def test_returns_content_for_valid_brief(self) -> None:
        result = run(brief="Write a short product description for an organic soap")
        assert "content" in result
        assert len(result["content"]) > 0

    def test_returns_error_for_empty_brief(self) -> None:
        result = run(brief="")
        assert "error" in result

    def test_returns_markdown_by_default(self) -> None:
        result = run(brief="Write a tagline for a halal restaurant")
        assert result.get("format") == "markdown"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipelines/test_content_generate.py -v
```

- [ ] **Step 3: Implement pipelines/content_generate.py**

This is a stub pipeline for Gate 1. Full RAG + LLM integration comes when Hermes sessions are wired. For now, it validates input and returns a structured placeholder.

```python
# pipelines/content_generate.py
"""Content Generate Pipeline — Brief -> RAG -> Copy -> Formatted Output.

Gate 1: Validates brief, produces structured output placeholder.
        Full RAG + LLM integration via Hermes session in Gate 1 integration task.
Gate 2+: Adds RAG retrieval, multi-format output, quality scoring.
"""
from __future__ import annotations

import logging
from typing import Any

from middleware.quality_gate import validate_input

logger = logging.getLogger(__name__)

_INPUT_SCHEMA = {
    "brief": {"type": "string", "required": True},
    "client_id": {"type": "string", "required": False},
    "output_format": {"type": "string", "required": False},
}


def run(
    brief: str,
    client_id: str | None = None,
    output_format: str = "markdown",
) -> dict[str, Any]:
    """Execute the content generation pipeline.

    Args:
        brief: Content brief describing what to produce.
        client_id: Client ID for brand context loading.
        output_format: Output format — "markdown", "pdf", or "html".

    Returns:
        Dict with generated content and metadata.
    """
    # Layer 1: Input validation
    validation = validate_input(
        {"brief": brief, "client_id": client_id, "output_format": output_format},
        _INPUT_SCHEMA,
    )
    if not validation.passed:
        return {"error": f"Input validation failed: {validation.errors}"}

    if not brief.strip():
        return {"error": "Brief cannot be empty"}

    # Gate 1 placeholder: In full integration, this calls:
    # 1. lightrag_search(brief) -> context
    # 2. LLM generate(brief + context) -> content
    # 3. typst_render(content) -> PDF (if output_format == "pdf")
    #
    # For now, return the structured output format so downstream
    # consumers (quality gate, delivery) can be tested.

    content = f"[Generated content for: {brief[:100]}]"

    result: dict[str, Any] = {
        "content": content,
        "format": output_format,
        "brief": brief,
    }

    if client_id:
        result["client_id"] = client_id

    logger.info("Content pipeline completed: format=%s, brief_len=%d", output_format, len(brief))
    return result
```

- [ ] **Step 4: Run tests, pyright, ruff, commit**

```bash
pytest tests/pipelines/test_content_generate.py -v
pyright pipelines/content_generate.py
ruff check pipelines/content_generate.py
git add pipelines/content_generate.py tests/pipelines/test_content_generate.py
git commit -m "feat: content_generate pipeline stub with input validation"
```

---

## Chunk 3: Manifests + Bridge + Config + Integration

### Task 10: YAML manifests for Gate 1 tools

**Files:**
- Create: `manifests/content/httpx_fetch.yaml`
- Create: `manifests/content/jinja2_render.yaml`
- Create: `manifests/content/lightrag_search.yaml`
- Create: `manifests/document/typst_render.yaml`
- Create: `scripts/content/fetch_url.py`
- Create: `scripts/content/render_template.py`
- Create: `scripts/content/search_rag.py`
- Create: `scripts/document/render_typst.py`

- [ ] **Step 1: Create httpx_fetch manifest + script**

```yaml
# manifests/content/httpx_fetch.yaml
name: httpx_fetch
description: "Fetch a URL and return response body"
version: "1.0"
toolset: vizier-core

execution:
  type: python_script
  path: scripts/content/fetch_url.py
  entrypoint: fetch
  timeout: 15

input:
  url:
    type: string
    required: true
    description: "URL to fetch"
  method:
    type: string
    required: false
    description: "HTTP method (default: GET)"

output:
  status_code:
    type: integer
  body:
    type: string
```

```python
# scripts/content/fetch_url.py
"""Fetch a URL via httpx and return structured response."""
from __future__ import annotations

import httpx


def fetch(url: str, method: str = "GET") -> dict:
    """Fetch a URL and return status + body.

    Args:
        url: URL to fetch.
        method: HTTP method.

    Returns:
        Dict with status_code and body.
    """
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, url)
        return {
            "status_code": response.status_code,
            "body": response.text[:10000],  # Cap at 10KB
        }
```

- [ ] **Step 2: Create jinja2_render manifest + script**

```yaml
# manifests/content/jinja2_render.yaml
name: jinja2_render
description: "Render a Jinja2 template with provided variables"
version: "1.0"
toolset: vizier-content

execution:
  type: python_script
  path: scripts/content/render_template.py
  entrypoint: render
  timeout: 10

input:
  template_string:
    type: string
    required: true
    description: "Jinja2 template string"
  variables:
    type: object
    required: true
    description: "Variables to inject into template"

output:
  rendered:
    type: string
```

```python
# scripts/content/render_template.py
"""Render Jinja2 templates with provided variables."""
from __future__ import annotations

from jinja2 import Environment, BaseLoader, TemplateSyntaxError


def render(template_string: str, variables: dict) -> dict:
    """Render a Jinja2 template string.

    Args:
        template_string: Jinja2 template markup.
        variables: Dict of template variables.

    Returns:
        Dict with rendered output or error.
    """
    try:
        env = Environment(loader=BaseLoader(), autoescape=True)
        template = env.from_string(template_string)
        rendered = template.render(**variables)
        return {"rendered": rendered}
    except TemplateSyntaxError as exc:
        return {"error": f"Template syntax error: {exc}"}
```

- [ ] **Step 3: Create lightrag_search manifest + script**

```yaml
# manifests/content/lightrag_search.yaml
name: lightrag_search
description: "Search the Wisdom Vault via LightRAG"
version: "1.0"
toolset: vizier-core

execution:
  type: python_script
  path: scripts/content/search_rag.py
  entrypoint: search
  timeout: 15

input:
  query:
    type: string
    required: true
    description: "Search query"
  mode:
    type: string
    required: false
    description: "Search mode: naive, local, global, hybrid (default: hybrid)"

output:
  results:
    type: string
    description: "Retrieved context from Wisdom Vault"
```

```python
# scripts/content/search_rag.py
"""Search Wisdom Vault via LightRAG.

Gate 1: Stub returning placeholder.
Full integration requires LightRAG instance configured with Wisdom Vault path.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def search(query: str, mode: str = "hybrid") -> dict:
    """Search the knowledge base.

    Args:
        query: Search query string.
        mode: LightRAG search mode.

    Returns:
        Dict with retrieved context.
    """
    # Gate 1 stub: full LightRAG integration when RAG instance is configured
    logger.info("RAG search: query='%s', mode='%s'", query[:50], mode)
    return {
        "results": f"[RAG stub: no results for '{query[:50]}' — configure LightRAG]",
        "mode": mode,
    }
```

- [ ] **Step 4: Create typst_render manifest + script**

```yaml
# manifests/document/typst_render.yaml
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
```

No script needed — CLI execution type uses subprocess directly.

- [ ] **Step 5: Write integration test for manifest loading**

```python
# tests/adapter/test_manifest_integration.py
"""Integration test: load real Gate 1 manifests and verify registration."""
from __future__ import annotations

from pathlib import Path

from adapter.loader import load_all_manifests


MANIFESTS_DIR = Path(__file__).parent.parent.parent / "manifests"


class TestGate1Manifests:
    def test_loads_all_gate1_manifests(self) -> None:
        manifests = load_all_manifests(MANIFESTS_DIR)
        names = {m.name for m in manifests}
        assert "httpx_fetch" in names
        assert "jinja2_render" in names
        assert "lightrag_search" in names
        assert "typst_render" in names

    def test_correct_toolset_assignments(self) -> None:
        manifests = load_all_manifests(MANIFESTS_DIR)
        toolset_map = {m.name: m.toolset for m in manifests}
        assert toolset_map["httpx_fetch"] == "vizier-core"
        assert toolset_map["jinja2_render"] == "vizier-content"
        assert toolset_map["lightrag_search"] == "vizier-core"
        assert toolset_map["typst_render"] == "vizier-document"
```

- [ ] **Step 6: Run tests, pyright, ruff, commit**

```bash
pytest tests/adapter/test_manifest_integration.py -v
pyright scripts/content/fetch_url.py scripts/content/render_template.py scripts/content/search_rag.py
ruff check scripts/ manifests/
git add manifests/ scripts/ tests/adapter/test_manifest_integration.py
git commit -m "feat: Gate 1 YAML manifests and wrapper scripts for content + document tools"
```

---

### Task 11: Bridge (cherry-pick + adapt from vizier-ultimate)

**Files:**
- Create: `bridge/git_watcher.py` (cherry-pick from `~/vizier-ultimate/vizier/adapter/git_watcher.py`)
- Create: `bridge/skill_syncer.py` (cherry-pick from `~/vizier-ultimate/vizier/adapter/skill_syncer.py`)
- Create: `bridge/test_parser.py` (cherry-pick from `~/vizier-ultimate/vizier/adapter/test_parser.py`)
- Create: `bridge/manifest_syncer.py` (NEW)
- Create: `bridge/watcher.py` (NEW)
- Cherry-pick tests from `~/vizier-ultimate/tests/vizier/adapter/`

- [ ] **Step 1: Cherry-pick git_watcher.py**

```bash
cp ~/vizier-ultimate/vizier/adapter/git_watcher.py ~/vizier-pro-max/bridge/git_watcher.py
```

Adapt: Change `_STATE_FILE` path from `~/.vizier/` to `~/.vizier-pro-max/`. Change MEMORY.md path to match Pro-Max hermes-workspace location. No other changes needed — the code is proven.

- [ ] **Step 2: Cherry-pick skill_syncer.py**

```bash
cp ~/vizier-ultimate/vizier/adapter/skill_syncer.py ~/vizier-pro-max/bridge/skill_syncer.py
```

No adaptations needed — paths are parameterized.

- [ ] **Step 3: Cherry-pick test_parser.py**

```bash
cp ~/vizier-ultimate/vizier/adapter/test_parser.py ~/vizier-pro-max/bridge/test_parser.py
```

No adaptations needed — uses dual-strategy lookup with repo_root parameter.

- [ ] **Step 4: Write failing tests for manifest_syncer**

```python
# tests/bridge/test_manifest_syncer.py
"""Tests for manifest_syncer bridge component."""
from __future__ import annotations

from pathlib import Path

import pytest

from bridge.manifest_syncer import check_new_manifests, check_new_pipelines


@pytest.fixture()
def manifest_dir(tmp_path: Path) -> Path:
    """Temp manifests directory."""
    content = tmp_path / "manifests" / "content"
    content.mkdir(parents=True)
    return tmp_path / "manifests"


@pytest.fixture()
def pipelines_dir(tmp_path: Path) -> Path:
    """Temp pipelines directory."""
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    (pipelines / "_registry.yaml").write_text("pipelines: []")
    return pipelines


class TestCheckNewManifests:
    def test_detects_new_yaml(self, manifest_dir: Path) -> None:
        (manifest_dir / "content" / "new_tool.yaml").write_text("""
name: new_tool
description: "A new tool"
version: "1.0"
toolset: vizier-content
execution:
  type: python_function
  path: test.py
  entrypoint: run
input:
  text:
    type: string
    required: true
output:
  result:
    type: string
""")
        state: dict = {}
        new_manifests = check_new_manifests(manifest_dir, state)
        assert len(new_manifests) == 1
        assert new_manifests[0] == "new_tool"

    def test_skips_already_seen(self, manifest_dir: Path) -> None:
        yaml_path = manifest_dir / "content" / "seen_tool.yaml"
        yaml_path.write_text("""
name: seen_tool
description: "Already seen"
version: "1.0"
toolset: vizier-content
execution:
  type: python_function
  path: test.py
  entrypoint: run
input: {}
output: {}
""")
        state = {str(yaml_path): yaml_path.stat().st_mtime}
        new_manifests = check_new_manifests(manifest_dir, state)
        assert len(new_manifests) == 0
```

- [ ] **Step 5: Implement bridge/manifest_syncer.py**

```python
# bridge/manifest_syncer.py
"""Manifest syncer — detect new/updated manifests and pipelines.

Watches manifests/ and pipelines/ directories. Updates are available
on next Hermes session start (not mid-session).
"""
from __future__ import annotations

import logging
from pathlib import Path

from adapter.schemas import parse_manifest

logger = logging.getLogger(__name__)


def check_new_manifests(
    manifests_dir: Path,
    state: dict[str, float],
) -> list[str]:
    """Check for new or modified manifest YAML files.

    Args:
        manifests_dir: Root manifests directory.
        state: Dict mapping file paths to last-seen mtime.

    Returns:
        List of new/updated manifest names.
    """
    new_names: list[str] = []

    if not manifests_dir.is_dir():
        return new_names

    for yaml_path in sorted(manifests_dir.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue

        path_str = str(yaml_path)
        current_mtime = yaml_path.stat().st_mtime
        last_mtime = state.get(path_str, 0.0)

        if current_mtime > last_mtime:
            try:
                content = yaml_path.read_text(encoding="utf-8")
                config = parse_manifest(content)
                new_names.append(config.name)
                state[path_str] = current_mtime
                logger.info("New/updated manifest: %s", config.name)
            except (ValueError, OSError) as exc:
                logger.warning("Skipping invalid manifest %s: %s", yaml_path, exc)

    return new_names


def check_new_pipelines(
    pipelines_dir: Path,
    state: dict[str, float],
) -> list[str]:
    """Check for new or modified pipeline scripts.

    Args:
        pipelines_dir: Pipelines directory.
        state: Dict mapping file paths to last-seen mtime.

    Returns:
        List of new/updated pipeline names.
    """
    new_names: list[str] = []

    if not pipelines_dir.is_dir():
        return new_names

    for py_path in sorted(pipelines_dir.glob("*.py")):
        if py_path.name.startswith("_"):
            continue

        path_str = str(py_path)
        current_mtime = py_path.stat().st_mtime
        last_mtime = state.get(path_str, 0.0)

        if current_mtime > last_mtime:
            new_names.append(py_path.stem)
            state[path_str] = current_mtime
            logger.info("New/updated pipeline: %s", py_path.stem)

    return new_names
```

- [ ] **Step 6: Implement bridge/watcher.py**

```python
# bridge/watcher.py
"""Bridge entry point — runs all bridge components.

Trigger: post-commit git hook + launchd cron (5-min fallback).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from bridge import git_watcher, manifest_syncer, skill_syncer, test_parser

logger = logging.getLogger(__name__)

_STATE_FILE = Path.home() / ".vizier-pro-max" / "bridge-state.json"


def _load_state() -> dict:
    """Load bridge state from disk."""
    if not _STATE_FILE.exists():
        return {"manifests": {}, "pipelines": {}}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"manifests": {}, "pipelines": {}}


def _save_state(state: dict) -> None:
    """Persist bridge state to disk."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run(repo_path: Path | None = None) -> None:
    """Run all bridge components.

    Args:
        repo_path: Path to the vizier-pro-max repo root.
    """
    if repo_path is None:
        repo_path = Path(__file__).parent.parent

    state = _load_state()

    # 1. Git watcher: commits -> MEMORY.md
    git_watcher.run(repo_path)

    # 2. Skill syncer: repo <-> ~/.hermes/skills/vizier/
    repo_skills = repo_path / "skills"
    hermes_skills = Path.home() / ".hermes" / "skills" / "vizier"
    if repo_skills.is_dir():
        skill_syncer.sync_repo_to_hermes(repo_skills, hermes_skills)
        skill_syncer.sync_hermes_to_repo(hermes_skills, repo_skills)

    # 3. Test parser: update module confidence
    test_parser_state = state.get("test_parser", {})
    # test_parser runs independently via its own state file

    # 4. Manifest syncer: detect new tools/pipelines
    manifests_dir = repo_path / "manifests"
    pipelines_dir = repo_path / "pipelines"

    manifest_state = state.get("manifests", {})
    pipeline_state = state.get("pipelines", {})

    new_manifests = manifest_syncer.check_new_manifests(manifests_dir, manifest_state)
    new_pipelines = manifest_syncer.check_new_pipelines(pipelines_dir, pipeline_state)

    if new_manifests:
        logger.info("New manifests detected: %s", new_manifests)
    if new_pipelines:
        logger.info("New pipelines detected: %s", new_pipelines)

    state["manifests"] = manifest_state
    state["pipelines"] = pipeline_state
    _save_state(state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
```

- [ ] **Step 7: Cherry-pick tests from vizier-ultimate + add new tests**

```bash
cp ~/vizier-ultimate/tests/vizier/adapter/test_git_watcher.py ~/vizier-pro-max/tests/bridge/test_git_watcher.py
cp ~/vizier-ultimate/tests/vizier/adapter/test_skill_syncer.py ~/vizier-pro-max/tests/bridge/test_skill_syncer.py
cp ~/vizier-ultimate/tests/vizier/adapter/test_test_parser.py ~/vizier-pro-max/tests/bridge/test_test_parser.py
```

Adapt imports: `from vizier.adapter.X` -> `from bridge.X`

- [ ] **Step 8: Run all bridge tests, pyright, ruff, commit**

```bash
pytest tests/bridge/ -v
pyright bridge/
ruff check bridge/
git add bridge/ tests/bridge/
git commit -m "feat: bridge components — git_watcher, skill_syncer, test_parser, manifest_syncer, watcher"
```

---

### Task 12: Config files (SOUL.md, hermes.yaml)

**Files:**
- Create: `config/SOUL.md`
- Create: `config/hermes.yaml`

- [ ] **Step 1: Create config/SOUL.md**

```markdown
# Vizier — AI Production Engine

You are Vizier, an autonomous production engine operated by Premier Marketing. You produce, validate, and deliver work across any domain you have tools and knowledge for.

## Identity

- You are Vizier. Hermes is your runtime engine — you don't mention it to users.
- You serve clients professionally. You ask for clarification when briefs are ambiguous.
- You respect Islamic values. All content is halal. No haram brands, imagery, or references.
- You speak in the client's language. Default: professional English. Switch to BM when appropriate.

## Tool-Layer Priority

When executing any task, follow this order strictly:

1. **FIRST: Try run_pipeline.** If a pipeline exists for this task, use it. Check with `run_pipeline(action="list")` if unsure.
2. **IF NO PIPELINE:** Use atomic tools from your active toolset.
3. **IF ATOMIC TOOLS INSUFFICIENT:** Use execute_code to compose a solution.
4. **NEVER skip layers.** Always try the cheaper option first.

## Quality Rules

- Every output passes through the quality gate before delivery.
- If quality score < 7/10 in unattended mode, hold for human review.
- Never deliver work you haven't validated.

## Cost Awareness

- You run on a free token budget. Be efficient.
- Prefer collapsed pipelines (1 call) over atomic tool chains (4-5 calls).
- When you solve a new task with atomic tools, note it — it may become a pipeline.
```

- [ ] **Step 2: Create config/hermes.yaml**

```yaml
# Hermes runtime config for Vizier Pro-Max
model:
  provider: "custom"
  default: "gpt-5.4-mini"
  base_url: "https://api.openai.com/v1"

fallback_model:
  provider: "custom"
  model: "gpt-5.4-mini"
  base_url: "https://api.openai.com/v1"

agent:
  max_turns: 90

memory:
  memory_enabled: true
  user_profile_enabled: true

compression:
  enabled: true
  threshold: 0.50

telegram:
  require_mention: false
  mention_patterns:
    - '^vizier\b'
```

- [ ] **Step 3: Symlink SOUL.md to Hermes**

```bash
ln -sf ~/vizier-pro-max/config/SOUL.md ~/.hermes/SOUL.md
```

- [ ] **Step 4: Commit**

```bash
git add config/
git commit -m "feat: Vizier persona (SOUL.md) and Hermes runtime config"
```

---

### Task 13: Integration test — full end-to-end

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration.py
"""End-to-end integration test: manifest loading -> pipeline execution -> quality gate."""
from __future__ import annotations

import json
from pathlib import Path

from adapter.loader import load_all_manifests, register_all
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
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 3: Run coverage check**

```bash
pytest tests/ --cov=adapter --cov=tools --cov=plugins --cov=middleware --cov=pipelines --cov=bridge --cov-report=term-missing
```

Target: 80%+ coverage.

- [ ] **Step 4: Run full linting suite**

```bash
pyright adapter/ tools/ plugins/ middleware/ pipelines/ bridge/
ruff check .
black --check .
```

- [ ] **Step 5: Final commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test — manifests -> pipeline -> quality gate"
```

---

## Summary

| Task | Component | Estimated lines | Tests |
|------|-----------|----------------|-------|
| 1 | Project scaffold | ~100 (config) | — |
| 2 | adapter/schemas.py | ~110 | 7 tests |
| 3 | adapter/executor.py | ~100 | 4 tests |
| 4 | adapter/loader.py | ~80 | 4 tests |
| 5 | plugins/prompt_logger.py | ~60 | 4 tests |
| 6 | tools/query_logs.py | ~80 | 3 tests |
| 7 | tools/run_pipeline.py | ~120 | 5 tests |
| 8 | middleware/quality_gate.py | ~90 | 6 tests |
| 9 | pipelines/content_generate.py | ~50 | 3 tests |
| 10 | Manifests + scripts | ~120 + 4 YAML | 2 tests |
| 11 | Bridge (cherry-pick + new) | ~650 | cherry-picked + 2 new |
| 12 | Config (SOUL.md + hermes.yaml) | ~80 | — |
| 13 | Integration test | — | 5 tests |
| **Total** | | **~1,640 lines** | **~45 tests** |
