"""Tests for augments.selfbuild.promoter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from augments.selfbuild.promoter import PromotionResult, promote
from augments.selfbuild.tier_classifier import TierDecision


@pytest.fixture()
def tier_1_decision(tmp_path: Path) -> TierDecision:
    """Tier 1 decision with a pipeline artifact."""
    pipeline = tmp_path / "pipelines" / "search_rag_render.py"
    pipeline.parent.mkdir(parents=True)
    pipeline.write_text('"""Pipeline."""\ndef run(): pass\n')
    skill_dir = tmp_path / "pipelines" / "search_rag_render"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# test\n")
    return TierDecision(
        tier=1,
        reasons=["openspace_captured pipeline"],
        artifact_paths=[pipeline],
    )


@pytest.fixture()
def tier_2_decision(tmp_path: Path) -> TierDecision:
    """Tier 2 decision with a tool artifact."""
    tool = tmp_path / "tools" / "my_tool.py"
    tool.parent.mkdir(parents=True)
    tool.write_text('"""Tool."""\ndef run(): pass\n')
    skill_dir = tmp_path / "tools" / "my_tool"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# test\n")
    return TierDecision(
        tier=2,
        reasons=["new atomic tool"],
        artifact_paths=[tool],
    )


class TestPromotionResult:
    """PromotionResult is a frozen dataclass."""

    def test_frozen(self) -> None:
        result = PromotionResult(
            status="promoted", reasons=["safe"], artifact_paths=[Path("x")]
        )
        with pytest.raises(AttributeError):
            result.status = "rejected"  # type: ignore[misc]


class TestTier1Promotion:
    """Tier 1 + safety passes -> promoted."""

    def test_tier_1_safe_promotes(
        self, tier_1_decision: TierDecision, tmp_path: Path
    ) -> None:
        from augments.openspace.safety import SafetyResult

        with patch(
            "augments.selfbuild.promoter.check_skill_safety",
            return_value=SafetyResult(is_safe=True, reason="Passed all checks"),
        ):
            result = promote(
                tier_decision=tier_1_decision, drafts_dir=tmp_path / "_drafts"
            )
        assert result.status == "promoted"

    def test_tier_1_unsafe_rejects(
        self, tier_1_decision: TierDecision, tmp_path: Path
    ) -> None:
        from augments.openspace.safety import SafetyResult

        with patch(
            "augments.selfbuild.promoter.check_skill_safety",
            return_value=SafetyResult(is_safe=False, reason="Dangerous pattern"),
        ):
            result = promote(
                tier_decision=tier_1_decision, drafts_dir=tmp_path / "_drafts"
            )
        assert result.status == "rejected"
        assert any("dangerous" in r.lower() or "unsafe" in r.lower() for r in result.reasons)


class TestTier2Promotion:
    """Tier 2 + safety passes -> held in _drafts/."""

    def test_tier_2_safe_holds(
        self, tier_2_decision: TierDecision, tmp_path: Path
    ) -> None:
        from augments.openspace.safety import SafetyResult

        drafts_dir = tmp_path / "_drafts"
        with patch(
            "augments.selfbuild.promoter.check_skill_safety",
            return_value=SafetyResult(is_safe=True, reason="Passed all checks"),
        ):
            result = promote(tier_decision=tier_2_decision, drafts_dir=drafts_dir)
        assert result.status == "held"
        assert drafts_dir.exists()
        # Check artifacts were copied to drafts
        copied = list(drafts_dir.iterdir())
        assert len(copied) > 0

    def test_tier_2_unsafe_rejects(
        self, tier_2_decision: TierDecision, tmp_path: Path
    ) -> None:
        from augments.openspace.safety import SafetyResult

        with patch(
            "augments.selfbuild.promoter.check_skill_safety",
            return_value=SafetyResult(is_safe=False, reason="Shell injection risk"),
        ):
            result = promote(
                tier_decision=tier_2_decision, drafts_dir=tmp_path / "_drafts"
            )
        assert result.status == "rejected"
