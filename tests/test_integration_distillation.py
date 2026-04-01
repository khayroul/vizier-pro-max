"""E2E integration test for the DSPy distillation pipeline (Chunk 1 Task 4).

Tests the full pipeline: generate synthetic data -> collect -> compile ->
evaluate -> deploy, with all LLM calls mocked.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import dspy
import pytest
import yaml

from augments.distillation.collector import (
    CollectionResult,
    TrainingExample,
    collect,
)
from augments.distillation.compiler import CompilationResult, compile_program
from augments.distillation.deployer import DeploymentResult, deploy
from augments.distillation.evaluator import EvaluationReport, evaluate
from scripts.bootstrap.generate_synthetic_sessions import (
    generate_synthetic_sessions,
)

if TYPE_CHECKING:
    from collections.abc import Generator


TASK_TYPE = "task_classification"
SEED = 42
CONFIG_REL = Path("config/bootstrap/synthetic_sessions.yaml")


@pytest.fixture()
def project_root() -> Path:
    """Return the project root (two levels up from this test file)."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def synthetic_db(tmp_path: Path, project_root: Path) -> Path:
    """Create a temp SQLite DB populated with synthetic training sessions.

    Generates 3 rounds with different seeds to exceed the 200-row minimum
    for task_classification (the YAML config only produces 80 per run).
    """
    db_path = tmp_path / "prompt_log.db"
    config_path = project_root / CONFIG_REL
    total = 0
    for run_seed in (SEED, SEED + 1, SEED + 2):
        total += generate_synthetic_sessions(
            config_path=config_path,
            db_path=db_path,
            seed=run_seed,
        )
    assert total >= 600, f"Expected >= 600 total rows, got {total}"
    return db_path


@pytest.fixture()
def collected(synthetic_db: Path) -> CollectionResult:
    """Collect training examples from synthetic DB."""
    return collect(
        task_type=TASK_TYPE,
        db_path=synthetic_db,
        include_synthetic=True,
        seed=SEED,
    )


@pytest.fixture()
def program_dir(tmp_path: Path) -> Path:
    """Temp directory for compiled DSPy programs."""
    out = tmp_path / "distilled"
    out.mkdir()
    return out


@pytest.fixture()
def models_yaml(tmp_path: Path) -> Path:
    """Temp models.yaml config file (initially empty)."""
    path = tmp_path / "models.yaml"
    path.write_text(
        yaml.dump(
            {
                "default_model": "gpt-5.4-mini",
                "fallback_model": "qwen3.5:9b",
                "offline_mode": False,
                "distilled_tasks": {},
            },
            default_flow_style=False,
        )
    )
    return path


@pytest.fixture()
def distillation_config(tmp_path: Path) -> Path:
    """Temp distillation_config.yaml file."""
    path = tmp_path / "distillation_config.yaml"
    path.write_text(
        yaml.dump(
            {
                "tasks": {
                    TASK_TYPE: {
                        "status": "pending",
                        "min_examples": 200,
                    }
                }
            },
            default_flow_style=False,
        )
    )
    return path


def _make_mock_compiled_program(
    program_path: Path,
    accuracy: float,
    test_examples: list[dict[str, str]],
) -> MagicMock:
    """Build a mock DSPy program that returns correct answers at given accuracy.

    Args:
        program_path: Path where the program file will be created.
        test_examples: The test examples that the evaluator will iterate over.
        accuracy: Fraction of examples to answer correctly (0.0-1.0).

    Returns:
        A MagicMock that behaves like a callable DSPy program.
    """
    num_correct = math.floor(len(test_examples) * accuracy)

    def side_effect(input_text: str) -> MagicMock:
        """Return correct or wrong answer based on position in sequence."""
        result = MagicMock()
        # Find the matching example
        for idx, ex in enumerate(test_examples):
            if ex["input_text"] == input_text:
                if idx < num_correct:
                    result.output = ex["expected_output"]
                else:
                    result.output = "__WRONG_ANSWER__"
                return result
        # Fallback: wrong answer for unknown inputs
        result.output = "__UNKNOWN__"
        return result

    mock_program = MagicMock()
    mock_program.side_effect = side_effect
    mock_program.load = MagicMock()

    # Create a placeholder program file so load_program doesn't fail
    program_path.parent.mkdir(parents=True, exist_ok=True)
    program_path.write_text("{}")

    return mock_program


class TestDistillationPipelineE2E:
    """Full pipeline: synthetic data -> collect -> compile -> evaluate -> deploy."""

    def test_full_pipeline_success(
        self,
        collected: CollectionResult,
        program_dir: Path,
        models_yaml: Path,
        distillation_config: Path,
    ) -> None:
        """Pipeline succeeds: accuracy >= 90% results in deployment."""
        # -- Step 1: Verify collection --
        assert collected.total_count >= 80  # task_classification has 80 rows
        assert len(collected.train_set) > 0
        assert len(collected.test_set) > 0
        assert all(ex.task_type == TASK_TYPE for ex in collected.train_set)

        # -- Step 2: Compile with mocked DSPy LMs --
        program_path = program_dir / TASK_TYPE / "program.json"

        mock_compiled = MagicMock()
        mock_compiled.save = MagicMock()

        with (
            patch("augments.distillation.compiler.dspy.LM") as mock_lm_cls,
            patch(
                "augments.distillation.compiler.dspy.settings"
            ) as mock_settings,
            patch(
                "augments.distillation.compiler.dspy.BootstrapFewShot"
            ) as mock_bootstrap_cls,
        ):
            mock_lm_cls.return_value = MagicMock()
            mock_bootstrap = MagicMock()
            mock_bootstrap.compile.return_value = mock_compiled
            mock_bootstrap_cls.return_value = mock_bootstrap

            result = compile_program(
                train_examples=collected.train_set,
                task_type=TASK_TYPE,
                teacher_model="gpt-5.4-mini",
                student_model="qwen3.5:9b",
                output_dir=program_dir,
            )

        assert isinstance(result, CompilationResult)
        assert result.task_type == TASK_TYPE
        assert result.num_examples == len(collected.train_set)
        assert result.duration_seconds >= 0
        assert result.program_path == program_path
        mock_compiled.save.assert_called_once_with(str(program_path))

        # -- Step 3: Evaluate with 92% accuracy mock --
        test_dicts = [
            {"input_text": ex.input_text, "expected_output": ex.expected_output}
            for ex in collected.test_set
        ]

        mock_program = _make_mock_compiled_program(
            program_path=program_path,
            accuracy=0.92,
            test_examples=test_dicts,
        )

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_program,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=test_dicts,
                task_type=TASK_TYPE,
                model="qwen3.5:9b",
            )

        assert isinstance(report, EvaluationReport)
        assert report.task_type == TASK_TYPE
        assert report.accuracy >= 0.90
        assert report.recommendation == "deploy"
        assert report.total_examples == len(test_dicts)
        assert report.correct == math.floor(len(test_dicts) * 0.92)

        # -- Step 4: Deploy --
        deploy_result = deploy(
            task_type=TASK_TYPE,
            accuracy=report.accuracy,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert isinstance(deploy_result, DeploymentResult)
        assert deploy_result.status == "deployed"
        assert deploy_result.accuracy == report.accuracy
        assert deploy_result.deployed_at is not None

        # -- Step 5: Verify models.yaml has routing entry --
        updated_config = yaml.safe_load(models_yaml.read_text())
        assert TASK_TYPE in updated_config["distilled_tasks"]
        task_entry = updated_config["distilled_tasks"][TASK_TYPE]
        assert task_entry["model"] == "qwen3.5:9b"
        assert task_entry["accuracy"] == report.accuracy
        assert task_entry["program_path"] == str(program_path)
        assert task_entry["deployed_at"] is not None

        # Verify distillation_config.yaml updated
        dist_config = yaml.safe_load(distillation_config.read_text())
        assert dist_config["tasks"][TASK_TYPE]["status"] == "deployed"

    def test_failure_path_low_accuracy(
        self,
        collected: CollectionResult,
        program_dir: Path,
        models_yaml: Path,
        distillation_config: Path,
    ) -> None:
        """When accuracy < 90%, deployer rejects and models.yaml is unchanged."""
        program_path = program_dir / TASK_TYPE / "program.json"

        test_dicts = [
            {"input_text": ex.input_text, "expected_output": ex.expected_output}
            for ex in collected.test_set
        ]

        # -- Evaluate with 85% accuracy --
        mock_program = _make_mock_compiled_program(
            program_path=program_path,
            accuracy=0.85,
            test_examples=test_dicts,
        )

        with patch(
            "augments.distillation.evaluator._load_program",
            return_value=mock_program,
        ):
            report = evaluate(
                program_path=program_path,
                test_examples=test_dicts,
                task_type=TASK_TYPE,
                model="qwen3.5:9b",
            )

        assert report.accuracy < 0.90
        assert report.recommendation == "hold"

        # Save original models.yaml content for comparison
        original_content = models_yaml.read_text()

        # -- Deploy should reject --
        deploy_result = deploy(
            task_type=TASK_TYPE,
            accuracy=report.accuracy,
            program_path=program_path,
            models_yaml_path=models_yaml,
            distillation_config_path=distillation_config,
        )

        assert deploy_result.status == "rejected"
        assert deploy_result.accuracy == report.accuracy
        assert deploy_result.deployed_at is None

        # models.yaml should be unchanged
        assert models_yaml.read_text() == original_content
        config = yaml.safe_load(models_yaml.read_text())
        assert config["distilled_tasks"] == {}


class TestCollectorIntegration:
    """Collector-specific integration tests with synthetic data."""

    def test_collect_returns_correct_split(self, synthetic_db: Path) -> None:
        """Train/test split is approximately 80/20."""
        result = collect(
            task_type=TASK_TYPE,
            db_path=synthetic_db,
            include_synthetic=True,
            seed=SEED,
        )
        expected_train = int(result.total_count * 0.8)
        assert len(result.train_set) == expected_train
        assert len(result.test_set) == result.total_count - expected_train

    def test_collect_insufficient_data_raises(self, tmp_path: Path) -> None:
        """Collecting from an empty DB raises InsufficientDataError."""
        import sqlite3

        from augments.distillation.collector import InsufficientDataError

        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE training_sessions ("
            "session_id TEXT PRIMARY KEY, "
            "timestamp REAL, "
            "input_message TEXT, "
            "task_type TEXT, "
            "toolset_chosen TEXT, "
            "pipeline_used TEXT, "
            "tool_calls TEXT, "
            "success INTEGER, "
            "synthetic INTEGER)"
        )
        conn.commit()
        conn.close()

        with pytest.raises(InsufficientDataError):
            collect(
                task_type=TASK_TYPE,
                db_path=db_path,
                include_synthetic=True,
                seed=SEED,
            )

    def test_deterministic_with_same_seed(self, synthetic_db: Path) -> None:
        """Same seed produces identical train/test splits."""
        result_a = collect(
            task_type=TASK_TYPE, db_path=synthetic_db, seed=SEED
        )
        result_b = collect(
            task_type=TASK_TYPE, db_path=synthetic_db, seed=SEED
        )
        assert [e.input_text for e in result_a.train_set] == [
            e.input_text for e in result_b.train_set
        ]
        assert [e.input_text for e in result_a.test_set] == [
            e.input_text for e in result_b.test_set
        ]
