"""Tests for pinned reference manifests."""
from __future__ import annotations

from references.inventory import list_reference_families, load_manifest


def test_all_expected_reference_families_present() -> None:
    assert list_reference_families() == ["quarto", "ui_ux_pro_max", "vega_lite"]


def test_manifests_have_required_metadata() -> None:
    for family in list_reference_families():
        manifest = load_manifest(family)
        assert manifest.display_name
        assert manifest.upstream_repo_url.startswith("https://github.com/")
        assert manifest.pinned_ref_type == "commit"
        assert len(manifest.pinned_ref) == 40
        assert manifest.license_name
        assert manifest.import_date == "2026-04-02"
        assert manifest.runtime_boundary
        assert manifest.imported_assets
        assert manifest.excluded_assets
