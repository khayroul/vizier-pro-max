"""Inventory helpers for pinned upstream reference corpora."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REFERENCES_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ReferenceManifest:
    """Manifest metadata for an imported reference family."""

    family: str
    display_name: str
    upstream_repo_url: str
    pinned_ref: str
    pinned_ref_type: str
    license_name: str
    import_date: str
    rationale: str
    runtime_boundary: str
    imported_assets: list[dict[str, Any]]
    excluded_assets: list[dict[str, Any]]
    manifest_path: Path


@dataclass(frozen=True)
class DatasetInventory:
    """Shape summary for a normalized dataset."""

    dataset_id: str
    description: str
    record_count: int
    dataset_path: Path


@dataclass(frozen=True)
class ReferenceFamilyInventory:
    """Inventory summary for a family of normalized references."""

    manifest: ReferenceManifest
    datasets: list[DatasetInventory]


def _family_dir(family: str) -> Path:
    path = _REFERENCES_ROOT / family
    if not path.exists():
        msg = f"Unknown reference family: {family}"
        raise FileNotFoundError(msg)
    return path


def list_reference_families() -> list[str]:
    """List available pinned reference families."""
    return sorted(
        path.name
        for path in _REFERENCES_ROOT.iterdir()
        if path.is_dir() and (path / "manifest.yaml").exists()
    )


def load_manifest(family: str) -> ReferenceManifest:
    """Load a parsed manifest for a reference family."""
    manifest_path = _family_dir(family) / "manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    source = raw.get("source", {})
    pinned = source.get("pinned_ref", {})
    return ReferenceManifest(
        family=family,
        display_name=str(source.get("name", family)),
        upstream_repo_url=str(source.get("repo_url", "")),
        pinned_ref=str(pinned.get("value", "")),
        pinned_ref_type=str(pinned.get("type", "commit")),
        license_name=str(source.get("license", "")),
        import_date=str(source.get("import_date", "")),
        rationale=str(raw.get("rationale", "")),
        runtime_boundary=str(raw.get("runtime_boundary", "")),
        imported_assets=list(raw.get("imported_assets", [])),
        excluded_assets=list(raw.get("excluded_assets", [])),
        manifest_path=manifest_path,
    )


def load_normalized_dataset(family: str, dataset_id: str) -> dict[str, Any]:
    """Load a normalized dataset by family and dataset id."""
    dataset_path = _family_dir(family) / "normalized" / f"{dataset_id}.json"
    if not dataset_path.exists():
        msg = f"Dataset not found: {family}/{dataset_id}"
        raise FileNotFoundError(msg)
    return json.loads(dataset_path.read_text(encoding="utf-8"))


def _dataset_inventory(dataset_path: Path) -> DatasetInventory:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    return DatasetInventory(
        dataset_id=str(payload.get("dataset_id", dataset_path.stem)),
        description=str(payload.get("description", "")),
        record_count=int(payload.get("record_count", 0)),
        dataset_path=dataset_path,
    )


def build_reference_inventory() -> list[ReferenceFamilyInventory]:
    """Build an inventory of the local reference families and datasets."""
    inventory: list[ReferenceFamilyInventory] = []
    for family in list_reference_families():
        normalized_dir = _family_dir(family) / "normalized"
        datasets = [
            _dataset_inventory(path)
            for path in sorted(normalized_dir.glob("*.json"))
        ]
        inventory.append(
            ReferenceFamilyInventory(
                manifest=load_manifest(family),
                datasets=datasets,
            )
        )
    return inventory
