"""Swap distilled model into routing config when evaluation passes.

Updates config/models.yaml and config/distillation_config.yaml with
the newly deployed task type, accuracy, and timestamp.
Immutable: writes new config, does not mutate in place.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog
import yaml

log = structlog.get_logger(__name__)

ACCURACY_THRESHOLD = 0.90

DEFAULT_MODELS_CONFIG: dict[str, object] = {
    "default_model": "gpt-5.4-mini",
    "fallback_model": "qwen3.5:9b",
    "offline_mode": False,
    "distilled_tasks": {},
}


@dataclass(frozen=True)
class DeploymentResult:
    """Result of a deployment attempt."""

    task_type: str
    status: str  # "deployed" or "rejected"
    accuracy: float
    deployed_at: str | None
    models_yaml_path: Path


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically via temp file + rename.

    Args:
        path: Target file path.
        content: YAML string to write.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(parent),
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    tmp_path.rename(path)


def _load_yaml(path: Path, defaults: dict[str, object] | None = None) -> dict:  # type: ignore[type-arg]
    """Load YAML file, returning defaults if file doesn't exist.

    Args:
        path: Path to YAML file.
        defaults: Default dict to return/write if file is missing.

    Returns:
        Parsed YAML content as dict.
    """
    if not path.exists():
        if defaults is not None:
            return dict(defaults)
        return {}

    content = yaml.safe_load(path.read_text())
    if content is None:
        return dict(defaults) if defaults is not None else {}
    return dict(content)


def deploy(
    task_type: str,
    accuracy: float,
    program_path: Path,
    models_yaml_path: Path = Path("config/models.yaml"),
    distillation_config_path: Path = Path("config/distillation_config.yaml"),
) -> DeploymentResult:
    """Deploy a distilled model into routing config if evaluation passed.

    Refuses to deploy if accuracy is below threshold. Performs atomic
    writes to both config files.

    Args:
        task_type: Task type identifier.
        accuracy: Evaluation accuracy (0.0-1.0).
        program_path: Path to compiled DSPy program.
        models_yaml_path: Path to models.yaml config.
        distillation_config_path: Path to distillation_config.yaml.

    Returns:
        DeploymentResult with status and metadata.
    """
    log.info(
        "deploy_requested",
        task_type=task_type,
        accuracy=accuracy,
        program_path=str(program_path),
    )

    if accuracy < ACCURACY_THRESHOLD:
        log.warning(
            "deployment_rejected",
            task_type=task_type,
            accuracy=accuracy,
            threshold=ACCURACY_THRESHOLD,
        )
        return DeploymentResult(
            task_type=task_type,
            status="rejected",
            accuracy=accuracy,
            deployed_at=None,
            models_yaml_path=models_yaml_path,
        )

    deployed_at = datetime.now(tz=timezone.utc).isoformat()

    # Update models.yaml
    models_config = _load_yaml(models_yaml_path, defaults=DEFAULT_MODELS_CONFIG)
    distilled_tasks = dict(models_config.get("distilled_tasks", {}))
    distilled_tasks[task_type] = {
        "model": "qwen3.5:9b",
        "accuracy": accuracy,
        "program_path": str(program_path),
        "deployed_at": deployed_at,
    }
    new_models_config = {**models_config, "distilled_tasks": distilled_tasks}
    _atomic_write(
        models_yaml_path,
        yaml.dump(new_models_config, default_flow_style=False, sort_keys=False),
    )

    # Update distillation_config.yaml
    dist_config = _load_yaml(distillation_config_path)
    tasks = dict(dist_config.get("tasks", {}))
    if task_type in tasks:
        task_entry = dict(tasks[task_type])
        task_entry["status"] = "deployed"
        task_entry["deployed_at"] = deployed_at
        tasks[task_type] = task_entry
    new_dist_config = {**dist_config, "tasks": tasks}
    _atomic_write(
        distillation_config_path,
        yaml.dump(new_dist_config, default_flow_style=False, sort_keys=False),
    )

    log.info(
        "deployment_complete",
        task_type=task_type,
        accuracy=accuracy,
        deployed_at=deployed_at,
    )

    return DeploymentResult(
        task_type=task_type,
        status="deployed",
        accuracy=accuracy,
        deployed_at=deployed_at,
        models_yaml_path=models_yaml_path,
    )
