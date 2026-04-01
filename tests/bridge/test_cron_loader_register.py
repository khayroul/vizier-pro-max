"""Tests for cron_loader registration with Hermes scheduler."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from bridge.cron_loader import CronJobConfig, load_cron_configs, register_jobs


class TestCronLoaderRegister:
    def test_register_jobs_calls_scheduler(self, tmp_path: Path) -> None:
        """register_jobs calls Hermes scheduler for each config."""
        config_dir = tmp_path / "cron"
        config_dir.mkdir()
        (config_dir / "test.yaml").write_text(
            "id: test_job\nschedule: '0 8 * * *'\n"
            "prompt: Generate content\ntoolsets:\n  - vizier-content\n"
        )
        configs = load_cron_configs(config_dir)
        assert len(configs) == 1

        mock_scheduler = MagicMock()
        registered = register_jobs(configs, scheduler=mock_scheduler)
        assert registered == 1
        mock_scheduler.add_job.assert_called_once()

    def test_register_jobs_skips_invalid(self) -> None:
        """register_jobs skips configs that fail registration."""
        mock_scheduler = MagicMock()
        mock_scheduler.add_job.side_effect = ValueError("bad schedule")

        registered = register_jobs(
            [CronJobConfig(id="bad", schedule="invalid", prompt="x", toolsets=[])],
            scheduler=mock_scheduler,
        )
        assert registered == 0
