"""Load cron YAML configs and validate them."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import structlog  # type: ignore[import-untyped]
import yaml

logger = structlog.get_logger(__name__)

_REQUIRED_FIELDS = {"id", "schedule", "prompt", "toolsets"}


@dataclass(frozen=True)
class CronJobConfig:
    """Typed representation of a cron job YAML config."""

    id: str
    schedule: str
    prompt: str
    toolsets: list[str] = field(default_factory=list)
    pipeline: str | None = None
    budget_cap: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronJobConfig:
        """Construct from a raw dict, raising ValueError on bad data."""
        missing = _REQUIRED_FIELDS - set(data.keys())
        if missing:
            msg = f"Missing required fields: {missing}"
            raise ValueError(msg)
        return cls(
            id=str(data["id"]),
            schedule=str(data["schedule"]),
            prompt=str(data["prompt"]),
            toolsets=[str(t) for t in data.get("toolsets", [])],
            pipeline=str(data["pipeline"]) if data.get("pipeline") else None,
            budget_cap=(
                float(data["budget_cap"])
                if data.get("budget_cap") is not None
                else None
            ),
        )


class HermesScheduler(Protocol):
    """Minimal protocol for the Hermes scheduler."""

    def add_job(
        self,
        *,
        job_id: str,
        schedule: str,
        prompt: str,
        toolsets: list[str],
        budget_cap: float | None,
    ) -> None: ...


def load_cron_configs(config_dir: Path) -> list[CronJobConfig]:
    """Load and validate cron configs from a directory."""
    configs: list[CronJobConfig] = []

    if not config_dir.exists():
        return configs

    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if data is None:
                logger.debug("Empty cron config: %s", yaml_file)
                continue
            if not isinstance(data, dict):
                logger.warning("Invalid cron config (not a dict): %s", yaml_file)
                continue
            config = CronJobConfig.from_dict(data)
            configs.append(config)
            logger.info("Loaded cron config: %s", config.id)
        except (yaml.YAMLError, OSError, KeyError, ValueError) as exc:
            logger.warning("Failed to load cron config %s: %s", yaml_file, exc)

    return configs


def register_jobs(
    configs: list[CronJobConfig],
    scheduler: HermesScheduler,
) -> int:
    """Register cron configs with Hermes scheduler.

    Args:
        configs: Validated CronJobConfig instances from load_cron_configs.
        scheduler: Hermes scheduler instance (has add_job method).

    Returns:
        Number of successfully registered jobs.
    """
    registered = 0
    for config in configs:
        try:
            scheduler.add_job(
                job_id=config.id,
                schedule=config.schedule,
                prompt=config.prompt,
                toolsets=config.toolsets,
                budget_cap=config.budget_cap,
            )
            logger.info(
                "Registered cron job: %s (%s)", config.id, config.schedule
            )
            registered += 1
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Failed to register cron job %s: %s", config.id, exc)
    return registered
