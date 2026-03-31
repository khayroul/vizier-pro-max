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
