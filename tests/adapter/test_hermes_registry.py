"""Tests for loading Hermes registry from the pinned submodule path."""
from __future__ import annotations

from pathlib import Path

from adapter.hermes_registry import hermes_registry_path, load_hermes_registry


def test_hermes_registry_path_uses_project_root(tmp_path: Path) -> None:
    path = hermes_registry_path(tmp_path)
    assert path == tmp_path / "hermes-agent" / "tools" / "registry.py"


def test_load_hermes_registry_returns_none_when_file_missing(
    tmp_path: Path,
) -> None:
    assert load_hermes_registry(tmp_path) is None


def test_load_hermes_registry_loads_registry_object(tmp_path: Path) -> None:
    registry_path = tmp_path / "hermes-agent" / "tools" / "registry.py"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        "class DummyRegistry:\n"
        "    def register(self, *args, **kwargs):\n"
        "        return None\n"
        "\n"
        "registry = DummyRegistry()\n",
        encoding="utf-8",
    )

    registry = load_hermes_registry(tmp_path)
    assert registry is not None
    assert hasattr(registry, "register")
