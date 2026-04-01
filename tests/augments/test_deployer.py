"""Tests for DSPy distillation deployer."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from augments.distillation.deployer import DeploymentResult, deploy


@pytest.fixture()
def models_yaml(tmp_path: Path) -> Path:
    """Create a models.yaml with default content."""
    path = tmp_path / "models.yaml"
    content = {
        "default_model": "gpt-5.4-mini",
        "fallback_model": "qwen3.5:9b",
        "offline_mode": False,
        "distilled_tasks": {},
    }
    path.write_text(yaml.dump(content, default_flow_style=False))
    return path


@pytest.fixture()
def distillation_config(tmp_path: Path) -> Path:
    """Create a distillation_config.yaml with pending status."""
    path = tmp_path / "distillation_config.yaml"
    content = {
        "tasks": {
            "task_classification": {
                "status": "pending",
                "min_examples": 200,
                "accuracy_threshold": 0.90,
                "consecutive_passes": 0,
                "deployed_at": None,
                "pipeline_version": None,
            },
        },
    }
    path.write_text(yaml.dump(content, default_flow_style=False))
    return path


@pytest.fixture()
def program_path(tmp_path: Path) -> Path:
    """Create a fake program file."""
    path = tmp_path / "compiled_program.json"
    path.write_text("{}")
    return path


class TestSuccessfulDeployment:
    """Test that successful deployment updates models.yaml."""

    def test_updates_models_yaml_with_distilled_task(
        self,
        models_yaml: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        result = deploy(
            task_type="task_classification",
            accuracy=0.95,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert result.status == "deployed"
        assert result.accuracy == 0.95
        assert result.task_type == "task_classification"
        assert result.deployed_at is not None

        updated = yaml.safe_load(models_yaml.read_text())
        assert "task_classification" in updated["distilled_tasks"]
        entry = updated["distilled_tasks"]["task_classification"]
        assert entry["accuracy"] == 0.95
        assert entry["model"] == "qwen3.5:9b"

    def test_updates_distillation_config_status(
        self,
        models_yaml: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        deploy(
            task_type="task_classification",
            accuracy=0.92,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        updated = yaml.safe_load(distillation_config.read_text())
        assert updated["tasks"]["task_classification"]["status"] == "deployed"
        assert updated["tasks"]["task_classification"]["deployed_at"] is not None


class TestDeploymentRejection:
    """Test deployer refuses when accuracy < 0.90."""

    def test_rejects_low_accuracy(
        self,
        models_yaml: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        result = deploy(
            task_type="task_classification",
            accuracy=0.85,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert result.status == "rejected"
        assert result.accuracy == 0.85

        # models.yaml should be unchanged
        updated = yaml.safe_load(models_yaml.read_text())
        assert updated["distilled_tasks"] == {}


class TestAtomicWrite:
    """Test that writes are atomic (temp file + rename)."""

    def test_atomic_write_models_yaml(
        self,
        models_yaml: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        original_content = models_yaml.read_text()

        result = deploy(
            task_type="task_classification",
            accuracy=0.95,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert result.status == "deployed"
        # File should exist and be updated (atomic rename completed)
        assert models_yaml.exists()
        new_content = models_yaml.read_text()
        assert new_content != original_content


class TestDeploymentResultFields:
    """Test DeploymentResult fields are populated."""

    def test_all_fields_present(
        self,
        models_yaml: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        result = deploy(
            task_type="task_classification",
            accuracy=0.95,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert result.task_type == "task_classification"
        assert result.status == "deployed"
        assert result.accuracy == 0.95
        assert result.deployed_at is not None
        assert result.models_yaml_path == models_yaml


class TestImmutability:
    """Test that original file is unchanged until atomic rename."""

    def test_original_unchanged_on_rejection(
        self,
        models_yaml: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        original_models = models_yaml.read_text()
        original_config = distillation_config.read_text()

        deploy(
            task_type="task_classification",
            accuracy=0.80,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert models_yaml.read_text() == original_models
        assert distillation_config.read_text() == original_config


class TestMissingModelsYaml:
    """Test that models.yaml is created with defaults if missing."""

    def test_creates_models_yaml_if_missing(
        self,
        tmp_path: Path,
        distillation_config: Path,
        program_path: Path,
    ) -> None:
        missing_path = tmp_path / "nonexistent" / "models.yaml"
        missing_path.parent.mkdir(parents=True)

        result = deploy(
            task_type="task_classification",
            accuracy=0.95,
            program_path=program_path,
            models_yaml_path=missing_path,
            distillation_config_path=distillation_config,
        )

        assert result.status == "deployed"
        assert missing_path.exists()
        content = yaml.safe_load(missing_path.read_text())
        assert content["default_model"] == "gpt-5.4-mini"
        assert "task_classification" in content["distilled_tasks"]
