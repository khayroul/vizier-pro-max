"""Cost Config — loads cost tracking configuration from YAML."""
from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "cost_config.yaml"
_config_lock = threading.Lock()
_cached_config: dict[str, Any] | None = None


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load cost config from YAML. Cached after first load.

    Args:
        path: Override config path (for testing).

    Returns:
        Config dict with baselines, quality, traces, model_costs sections.
    """
    global _cached_config  # noqa: PLW0603
    if _cached_config is not None and path is None:
        return copy.deepcopy(_cached_config)

    with _config_lock:
        if _cached_config is not None and path is None:
            return copy.deepcopy(_cached_config)

        config_path = path or _CONFIG_PATH
        if not config_path.exists():
            logger.warning("Cost config not found at %s, using defaults", config_path)
            return _defaults()

        with config_path.open() as fh:
            config = yaml.safe_load(fh) or _defaults()

        if path is None:
            _cached_config = config
        return copy.deepcopy(config)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for a model call using configured rates.

    Args:
        model: Model identifier (e.g., "gpt-5.4-mini").
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Cost in dollars.
    """
    config = load_config()
    rates = config.get("model_costs", {}).get(model, {})
    input_rate = rates.get("input_per_1k", 0.0)
    output_rate = rates.get("output_per_1k", 0.0)
    return (input_tokens * input_rate / 1000.0) + (output_tokens * output_rate / 1000.0)


def _defaults() -> dict[str, Any]:
    """Return default config when YAML is missing."""
    return {
        "baselines": {
            "bootstrap_count": 20,
            "recalculate_interval": 10,
            "anomaly_stddev": 2.0,
        },
        "quality": {"min_score": 7.0},
        "traces": {
            "retention_days": 90,
            "archive_dir": "traces/archive",
            "export_dir": "traces",
        },
        "model_costs": {},
    }
