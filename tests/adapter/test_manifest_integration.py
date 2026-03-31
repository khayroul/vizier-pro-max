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
