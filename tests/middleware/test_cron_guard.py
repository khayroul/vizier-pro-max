"""Tests for cron_guard safety layer."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from middleware.cron_guard import check_job_safety, enforce_token_budget


class TestCronGuard:
    def test_allow_job_with_tested_tools(self) -> None:
        """Job passes when all tools have test files."""
        with patch("middleware.cron_guard._tools_have_tests") as mock:
            mock.return_value = True
            result = check_job_safety(
                toolsets=["vizier-core", "vizier-content"],
                token_budget=50000,
            )
        assert result["allowed"] is True

    def test_block_job_with_untested_tools(self) -> None:
        """Job blocked when tools lack test files."""
        with patch("middleware.cron_guard._tools_have_tests") as mock:
            mock.return_value = False
            result = check_job_safety(
                toolsets=["vizier-core", "vizier-content"],
                token_budget=50000,
            )
        assert result["allowed"] is False
        assert "untested" in result["reason"]

    def test_enforce_token_budget_within_limit(self) -> None:
        assert enforce_token_budget(used=30000, budget=50000) is True

    def test_enforce_token_budget_exceeded(self) -> None:
        assert enforce_token_budget(used=60000, budget=50000) is False

    def test_quality_threshold_hold(self) -> None:
        from middleware.cron_guard import should_hold_delivery

        assert should_hold_delivery(score=5.0, threshold=7.0) is True
        assert should_hold_delivery(score=8.0, threshold=7.0) is False
