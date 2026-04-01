"""Tests for augments.selfbuild.tier_classifier."""
from __future__ import annotations

from pathlib import Path

import pytest

from augments.selfbuild.tier_classifier import TierDecision, classify


@pytest.fixture()
def tmp_pipelines(tmp_path: Path) -> Path:
    """Create a temporary pipelines directory with a .py file."""
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    pipeline_file = pipelines_dir / "search_rag_render.py"
    pipeline_file.write_text('"""Auto-generated pipeline."""\ndef run(): pass\n')
    return pipeline_file


@pytest.fixture()
def tmp_tool_with_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """Create a temporary tool script and manifest."""
    tool_file = tmp_path / "tools" / "my_tool.py"
    tool_file.parent.mkdir(parents=True)
    tool_file.write_text('"""A new tool."""\ndef run(): pass\n')
    manifest_file = tmp_path / "manifests" / "code" / "my_tool.yaml"
    manifest_file.parent.mkdir(parents=True)
    manifest_file.write_text(
        "name: my_tool\n"
        "description: A new atomic tool\n"
        "version: '1.0'\n"
        "toolset: vizier-code\n"
    )
    return tool_file, manifest_file


@pytest.fixture()
def tmp_delivery_tool(tmp_path: Path) -> tuple[Path, Path]:
    """Create a tool with delivery toolset in manifest."""
    tool_file = tmp_path / "tools" / "send_sms.py"
    tool_file.parent.mkdir(parents=True, exist_ok=True)
    tool_file.write_text('"""Send SMS."""\ndef run(): pass\n')
    manifest_file = tmp_path / "manifests" / "delivery" / "send_sms.yaml"
    manifest_file.parent.mkdir(parents=True)
    manifest_file.write_text(
        "name: send_sms\n"
        "description: Send SMS via API\n"
        "version: '1.0'\n"
        "toolset: vizier-delivery\n"
    )
    return tool_file, manifest_file


class TestTierDecision:
    """TierDecision is a frozen dataclass."""

    def test_frozen(self) -> None:
        decision = TierDecision(tier=1, reasons=["test"], artifact_paths=[Path("x")])
        with pytest.raises(AttributeError):
            decision.tier = 2  # type: ignore[misc]


class TestClassifyPipelineFromOpenspace:
    """Pipeline collapse from openspace_captured -> Tier 1."""

    def test_pipeline_openspace_captured_is_tier_1(
        self, tmp_pipelines: Path
    ) -> None:
        result = classify(
            artifact_path=tmp_pipelines,
            manifest_path=None,
            origin="openspace_captured",
        )
        assert result.tier == 1
        assert any("openspace" in r.lower() or "pipeline" in r.lower() for r in result.reasons)

    def test_pipeline_without_openspace_origin_is_tier_2(
        self, tmp_pipelines: Path
    ) -> None:
        result = classify(
            artifact_path=tmp_pipelines,
            manifest_path=None,
            origin="manual",
        )
        assert result.tier == 2


class TestClassifyNewAtomicTool:
    """New atomic tool with manifest -> Tier 2."""

    def test_new_tool_with_manifest_is_tier_2(
        self, tmp_tool_with_manifest: tuple[Path, Path]
    ) -> None:
        tool_file, manifest_file = tmp_tool_with_manifest
        result = classify(
            artifact_path=tool_file,
            manifest_path=manifest_file,
            origin="manual",
        )
        assert result.tier == 2
        assert len(result.reasons) > 0


class TestClassifyDeliveryTool:
    """Tool with delivery toolset -> Tier 2."""

    def test_delivery_toolset_is_tier_2(
        self, tmp_delivery_tool: tuple[Path, Path]
    ) -> None:
        tool_file, manifest_file = tmp_delivery_tool
        result = classify(
            artifact_path=tool_file,
            manifest_path=manifest_file,
            origin="openspace_captured",
        )
        assert result.tier == 2
        assert any("delivery" in r.lower() for r in result.reasons)


class TestReadManifestToolsetEdgeCases:
    """Edge cases for _read_manifest_toolset."""

    def test_oserror_returns_none(self, tmp_path: Path) -> None:
        """OSError on file read returns None (lines 36-37)."""
        from augments.selfbuild.tier_classifier import _read_manifest_toolset

        nonexistent = tmp_path / "does_not_exist.yaml"
        assert _read_manifest_toolset(nonexistent) is None

    def test_no_toolset_key_returns_none(self, tmp_path: Path) -> None:
        """Manifest without a toolset key returns None (line 44)."""
        from augments.selfbuild.tier_classifier import _read_manifest_toolset

        manifest = tmp_path / "no_toolset.yaml"
        manifest.write_text("name: some_tool\ndescription: no toolset here\n")
        assert _read_manifest_toolset(manifest) is None


class TestClassifyConservativeDefault:
    """No manifest, no origin -> Tier 2 (conservative)."""

    def test_no_manifest_no_origin_is_tier_2(self, tmp_path: Path) -> None:
        artifact = tmp_path / "unknown_artifact.py"
        artifact.write_text("# something\n")
        result = classify(
            artifact_path=artifact,
            manifest_path=None,
            origin="",
        )
        assert result.tier == 2
        assert any("conservative" in r.lower() or "default" in r.lower() for r in result.reasons)
