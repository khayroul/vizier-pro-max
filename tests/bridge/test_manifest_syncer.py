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
        state: dict[str, float] = {}
        new_manifests, _updated_state = check_new_manifests(manifest_dir, state)
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
        state: dict[str, float] = {str(yaml_path): yaml_path.stat().st_mtime}
        new_manifests, _updated_state = check_new_manifests(manifest_dir, state)
        assert len(new_manifests) == 0


class TestCheckNewPipelines:
    def test_detects_new_pipeline(self, pipelines_dir: Path) -> None:
        (pipelines_dir / "new_pipeline.py").write_text("def run(): pass")
        state: dict[str, float] = {}
        new_pipelines, _updated_state = check_new_pipelines(pipelines_dir, state)
        assert len(new_pipelines) == 1
        assert new_pipelines[0] == "new_pipeline"

    def test_skips_already_seen_pipeline(self, pipelines_dir: Path) -> None:
        py_path = pipelines_dir / "old_pipeline.py"
        py_path.write_text("def run(): pass")
        state: dict[str, float] = {str(py_path): py_path.stat().st_mtime}
        new_pipelines, _updated_state = check_new_pipelines(pipelines_dir, state)
        assert len(new_pipelines) == 0
