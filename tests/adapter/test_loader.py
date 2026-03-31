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

    @patch("adapter.loader._get_registry")
    def test_skips_registration_when_no_registry(
        self, mock_get_registry: MagicMock, manifest_dir: Path
    ) -> None:
        mock_get_registry.return_value = None
        manifests = load_all_manifests(manifest_dir)
        # Should not raise even with no registry
        register_manifest(manifests[0])


class TestRegisterAll:
    @patch("adapter.loader._get_registry")
    def test_registers_all_valid_manifests(
        self, mock_get_registry: MagicMock, manifest_dir: Path
    ) -> None:
        from adapter.loader import register_all

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        count = register_all(manifest_dir)
        assert count == 1
        mock_registry.register.assert_called_once()

    @patch("adapter.loader._get_registry")
    def test_returns_zero_for_empty_dir(
        self, mock_get_registry: MagicMock, tmp_path: Path
    ) -> None:
        from adapter.loader import register_all

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        count = register_all(tmp_path / "nonexistent")
        assert count == 0

    @patch("adapter.loader._get_registry")
    def test_continues_when_one_manifest_fails_to_register(
        self, mock_get_registry: MagicMock, tmp_path: Path
    ) -> None:
        from adapter.loader import register_all

        # Create two valid manifests
        for name in ("tool_a", "tool_b"):
            (tmp_path / f"{name}.yaml").write_text(f"""
name: {name}
description: "Tool {name}"
version: "1.0"
toolset: vizier-core
execution:
  type: python_script
  path: scripts/{name}.py
  entrypoint: run
  timeout: 10
input:
  x:
    type: string
    required: true
""")

        mock_registry = MagicMock()
        # First call succeeds, second raises
        mock_registry.register.side_effect = [None, RuntimeError("registry boom")]
        mock_get_registry.return_value = mock_registry

        # Should return 1 (only one succeeded)
        count = register_all(tmp_path)
        assert count == 1

    def test_get_registry_returns_none_when_unavailable(self) -> None:
        from adapter.loader import _get_registry

        # The import of tools.registry will fail in test env — should return None
        with patch("adapter.loader._get_registry", return_value=None):
            result = _get_registry()
            assert result is None
