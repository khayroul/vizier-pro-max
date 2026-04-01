"""Integration tests for self-building code workflow (Gate 3 Chunk 2)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from augments.openspace.safety import SafetyResult
from augments.selfbuild.notifier import notify_human
from augments.selfbuild.promoter import promote
from augments.selfbuild.tier_classifier import classify


class TestTier1FullFlow:
    """Full Tier 1 flow: pipeline from openspace -> classify -> promote."""

    def test_pipeline_auto_promotes(self, tmp_path: Path) -> None:
        # 1. Create mock artifact (pipeline .py file)
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        pipeline_file = pipelines_dir / "search_rag_render.py"
        pipeline_file.write_text('"""Auto-generated pipeline."""\ndef run(): pass\n')

        # Create skill dir for safety check
        skill_dir = pipelines_dir / "search_rag_render"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# test\n")

        # 2. Tier classifier -> Tier 1
        decision = classify(
            artifact_path=pipeline_file,
            manifest_path=None,
            origin="openspace_captured",
        )
        assert decision.tier == 1

        # 3. Promoter: safety check passes -> "promoted"
        with patch(
            "augments.selfbuild.promoter.check_skill_safety",
            return_value=SafetyResult(is_safe=True, reason="Passed all checks"),
        ):
            result = promote(
                tier_decision=decision, drafts_dir=tmp_path / "_drafts"
            )

        # 4. Verify result
        assert result.status == "promoted"


class TestTier2FullFlow:
    """Full Tier 2 flow: new tool -> classify -> hold -> notify."""

    def test_new_tool_held_and_notified(self, tmp_path: Path) -> None:
        # 1. Create mock artifact (new atomic tool with manifest)
        tool_file = tmp_path / "tools" / "my_tool.py"
        tool_file.parent.mkdir(parents=True)
        tool_file.write_text('"""New tool."""\ndef run(): pass\n')

        manifest_file = tmp_path / "manifests" / "code" / "my_tool.yaml"
        manifest_file.parent.mkdir(parents=True)
        manifest_file.write_text(
            "name: my_tool\n"
            "description: A new tool\n"
            "version: '1.0'\n"
            "toolset: vizier-code\n"
        )

        # Create skill dir for safety check
        skill_dir = tmp_path / "tools" / "my_tool"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# test\n")

        # 2. Tier classifier -> Tier 2
        decision = classify(
            artifact_path=tool_file,
            manifest_path=manifest_file,
            origin="manual",
        )
        assert decision.tier == 2

        # 3. Promoter: safety passes -> "held" in _drafts/
        drafts_dir = tmp_path / "_drafts"
        with patch(
            "augments.selfbuild.promoter.check_skill_safety",
            return_value=SafetyResult(is_safe=True, reason="Passed all checks"),
        ):
            result = promote(tier_decision=decision, drafts_dir=drafts_dir)
        assert result.status == "held"
        assert drafts_dir.exists()

        # 4. Notifier called (mocked)
        with patch(
            "augments.selfbuild.notifier._send_telegram",
            return_value={"message_id": 42, "status": "sent"},
        ):
            notification = notify_human(
                artifact_paths=decision.artifact_paths,
                tier_decision=decision,
                chat_id="12345",
            )
        assert notification.sent is True
