"""Tests for cron_loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from bridge.cron_loader import load_cron_configs


class TestCronLoader:
    def test_load_valid_configs(self, tmp_path: Path) -> None:
        config = tmp_path / "test_job.yaml"
        config.write_text(
            "id: test_job\n"
            "schedule: '0 8 * * 1-5'\n"
            "prompt: 'Generate posts'\n"
            "toolsets:\n  - vizier-core\n  - vizier-content\n"
            "max_iterations: 30\n"
            "token_budget: 50000\n"
            "quality_threshold: 7\n"
        )
        configs = load_cron_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0]["id"] == "test_job"
        assert configs[0]["schedule"] == "0 8 * * 1-5"

    def test_skip_invalid_config(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: valid: cron: config\n")
        configs = load_cron_configs(tmp_path)
        assert len(configs) == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        configs = load_cron_configs(tmp_path)
        assert configs == []
