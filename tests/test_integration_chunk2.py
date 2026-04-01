"""E2E integration test for Chunk 2: all workflow toolsets."""
from __future__ import annotations

from pathlib import Path

from adapter.schemas import parse_manifest


class TestChunk2Integration:
    def test_all_new_manifests_parse(self) -> None:
        """Every new manifest is valid YAML with required fields."""
        manifest_dirs = [
            "manifests/visual",
            "manifests/research",
            "manifests/audio",
            "manifests/document",
        ]
        for dir_path in manifest_dirs:
            manifests_path = Path(dir_path)
            if not manifests_path.exists():
                continue
            for yaml_file in manifests_path.glob("*.yaml"):
                manifest = parse_manifest(yaml_file.read_text())
                assert manifest.name, f"Missing name in {yaml_file}"
                assert manifest.toolset, f"Missing toolset in {yaml_file}"
                assert manifest.execution, f"Missing execution in {yaml_file}"

    def test_pipeline_stubs_callable(self) -> None:
        """All pipeline stubs are importable and return stub status."""
        from pipelines.clone_converge import run as cc_run
        from pipelines.competitive_analysis import run as ca_run
        from pipelines.poster_batch import run as pb_run
        from pipelines.tts_generate import run as tts_run

        assert cc_run(target_image_path="/fake.png")["status"] == "stub"
        assert pb_run()["status"] == "stub"
        assert ca_run(topic="test")["status"] == "stub"
        assert tts_run(text="hello")["status"] == "stub"

    def test_toolset_names_match_manifests(self) -> None:
        """Manifest toolset fields match expected toolset names."""
        for yaml_file in Path("manifests").rglob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            manifest = parse_manifest(yaml_file.read_text())
            toolset = manifest.toolset
            assert toolset.startswith("vizier-"), (
                f"{yaml_file}: toolset '{toolset}' doesn't start with 'vizier-'"
            )
