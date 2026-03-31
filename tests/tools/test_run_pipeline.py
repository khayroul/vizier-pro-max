"""Tests for run_pipeline Hermes tool."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tools.run_pipeline import load_pipeline_registry, run_pipeline


@pytest.fixture()
def pipeline_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create temp pipeline directory with registry and a sample pipeline."""
    monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)

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
        result = json.loads(
            run_pipeline({"name": "test_pipeline", "args": {"text": "hello"}})
        )
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

    def test_no_name_and_no_action_returns_error(self, pipeline_dir: Path) -> None:
        result = json.loads(run_pipeline({}))
        assert "error" in result
        assert "name" in result["error"].lower() or "list" in result["error"].lower()

    def test_missing_script_file_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)

        (tmp_path / "_registry.yaml").write_text("""
pipelines:
  - name: ghost_pipeline
    description: "Pipeline with no script"
""")
        # No ghost_pipeline.py created

        result = json.loads(run_pipeline({"name": "ghost_pipeline"}))
        assert "error" in result
        err = result["error"].lower()
        assert "script" in err or "not found" in err

    def test_pipeline_with_no_run_function_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)

        (tmp_path / "_registry.yaml").write_text("""
pipelines:
  - name: no_run
    description: "Pipeline without run()"
""")
        (tmp_path / "no_run.py").write_text("x = 42\n")

        result = json.loads(run_pipeline({"name": "no_run"}))
        assert "error" in result
        assert "run" in result["error"].lower()

    def test_pipeline_exception_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)

        (tmp_path / "_registry.yaml").write_text("""
pipelines:
  - name: crash_pipeline
    description: "Pipeline that crashes"
""")
        (tmp_path / "crash_pipeline.py").write_text(
            "def run(): raise ValueError('boom')\n"
        )

        result = json.loads(run_pipeline({"name": "crash_pipeline"}))
        assert "error" in result

    def test_pipeline_returning_string_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)

        (tmp_path / "_registry.yaml").write_text("""
pipelines:
  - name: str_pipeline
    description: "Returns a string"
""")
        (tmp_path / "str_pipeline.py").write_text("def run(): return 'done'\n")

        result = json.loads(run_pipeline({"name": "str_pipeline"}))
        assert result.get("result") == "done"

    def test_invalid_yaml_registry_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)
        (tmp_path / "_registry.yaml").write_text("pipelines: [[[")

        registry = load_pipeline_registry()
        assert registry == {}

    def test_registry_without_pipelines_key_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tools.run_pipeline.PIPELINES_DIR", tmp_path)
        (tmp_path / "_registry.yaml").write_text("other_key: value\n")

        registry = load_pipeline_registry()
        assert registry == {}
