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

    def test_execute_python_function_delegates_to_script(
        self, script_manifest: ManifestConfig
    ) -> None:
        """python_function execution type delegates to _execute_python_script."""
        # Build a manifest with type python_function pointing at same script
        func_yaml = f"""
name: echo_func
description: "Echo via function"
version: "1.0"
toolset: vizier-core
execution:
  type: python_function
  path: "{script_manifest.execution.path}"
  entrypoint: run
  timeout: 10
input:
  text:
    type: string
    required: true
"""
        from adapter.schemas import parse_manifest as pm

        func_manifest = pm(func_yaml)
        result = execute_tool(func_manifest, {"text": "world"})
        parsed = json.loads(result)
        assert parsed["echoed"] == "world"

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

    def test_cli_missing_command_rejected_at_parse(self) -> None:
        from adapter.schemas import parse_manifest as pm

        yaml_str = """
name: bad_cli
description: "CLI with no command"
version: "1.0"
toolset: vizier-core
execution:
  type: cli
  timeout: 5
input: {}
"""
        with pytest.raises(ValueError, match="(?i)command"):
            pm(yaml_str)

    def test_cli_missing_template_arg_returns_error(self) -> None:
        from adapter.schemas import parse_manifest as pm

        yaml_str = """
name: template_cli
description: "CLI with missing arg"
version: "1.0"
toolset: vizier-core
execution:
  type: cli
  command: "echo {missing_arg}"
  timeout: 5
input: {}
"""
        config = pm(yaml_str)
        result = execute_tool(config, {})
        parsed = json.loads(result)
        assert "error" in parsed

    def test_cli_nonzero_exit_returns_error(self, tmp_path: Path) -> None:
        from adapter.schemas import parse_manifest as pm

        yaml_str = """
name: failing_cli
description: "CLI that fails"
version: "1.0"
toolset: vizier-core
execution:
  type: cli
  command: "false"
  timeout: 5
input: {}
"""
        config = pm(yaml_str)
        result = execute_tool(config, {})
        parsed = json.loads(result)
        assert "error" in parsed

    def test_python_script_missing_path_rejected_at_parse(self) -> None:
        from adapter.schemas import parse_manifest as pm

        yaml_str = """
name: no_path
description: "Script with no path"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  timeout: 5
input: {}
"""
        with pytest.raises(ValueError, match="(?i)path.*entrypoint"):
            pm(yaml_str)

    def test_python_script_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        from adapter.schemas import parse_manifest as pm

        ghost = tmp_path / "ghost_tool.py"
        yaml_str = f"""
name: ghost_script
description: "Script pointing at nonexistent file"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: "{ghost}"
  entrypoint: run
  timeout: 5
input: {{}}
"""
        config = pm(yaml_str)
        result = execute_tool(config, {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "not found" in parsed["error"].lower()

    def test_python_script_missing_entrypoint_returns_error(
        self, tmp_path: Path
    ) -> None:
        from adapter.schemas import parse_manifest as pm

        script = tmp_path / "no_entry.py"
        script.write_text("x = 1\n")

        yaml_str = f"""
name: no_entry
description: "Script missing entrypoint"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: "{script}"
  entrypoint: does_not_exist
  timeout: 5
input: {{}}
"""
        config = pm(yaml_str)
        result = execute_tool(config, {})
        parsed = json.loads(result)
        assert "error" in parsed
        err = parsed["error"].lower()
        assert "entrypoint" in err or "not found" in err

    def test_python_script_returns_string_result(self, tmp_path: Path) -> None:
        from adapter.schemas import parse_manifest as pm

        script = tmp_path / "str_tool.py"
        script.write_text("def run(): return 'hello string'\n")

        yaml_str = f"""
name: str_tool
description: "Returns a plain string"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: "{script}"
  entrypoint: run
  timeout: 5
input: {{}}
"""
        config = pm(yaml_str)
        result = execute_tool(config, {})
        parsed = json.loads(result)
        assert parsed.get("result") == "hello string"
