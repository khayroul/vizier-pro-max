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
        assert len(manifests) == 1

    def test_returns_empty_for_missing_dir(self, tmp_path: Path) -> None:
        manifests = load_all_manifests(tmp_path / "nonexistent")
        assert manifests == []


class TestRegisterManifest:
    @patch("adapter.loader._get_registry")
    def test_calls_registry_register(
        self, mock_get_registry: MagicMock, manifest_dir: Path
    ) -> None:
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        manifests = load_all_manifests(manifest_dir)
        register_manifest(manifests[0])

        mock_registry.register.assert_called_once()
        call_kwargs = mock_registry.register.call_args
        assert call_kwargs[1]["name"] == "httpx_fetch"
        assert call_kwargs[1]["toolset"] == "vizier-core"
        assert "url" in call_kwargs[1]["schema"]["properties"]
