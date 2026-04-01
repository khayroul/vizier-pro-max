"""Load cron YAML configs and validate them."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"id", "schedule", "prompt", "toolsets"}


def load_cron_configs(config_dir: Path) -> list[dict[str, Any]]:
    """Load and validate cron configs from a directory."""
    configs: list[dict[str, Any]] = []

    if not config_dir.exists():
        return configs

    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text())
            if not isinstance(data, dict):
                logger.warning("Invalid cron config (not a dict): %s", yaml_file)
                continue
            missing = _REQUIRED_FIELDS - set(data.keys())
            if missing:
                logger.warning("Cron config %s missing fields: %s", yaml_file, missing)
                continue
            configs.append(data)
            logger.info("Loaded cron config: %s", data["id"])
        except Exception as exc:
            logger.warning("Failed to load cron config %s: %s", yaml_file, exc)

    return configs
