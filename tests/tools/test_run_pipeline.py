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
