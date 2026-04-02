"""Tests for DSPy compiler — program definition + compilation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy
import pytest

from augments.distillation.collector import TrainingExample
from augments.distillation.compiler import (
    CompilationResult,
    ToolsetClassifier,
    _toolset_match_metric,
    build_distillation_lm,
    compile_program,
    distillation_gateway_base_url,
    load_program,
)

TASK_TYPE = "task_classification"
VALID_TOOLSETS = ["search_rag", "code_gen", "template_render", "http_fetch"]


@pytest.fixture()
def train_examples() -> list[TrainingExample]:
    """Generate 50 training examples for tests."""
    return [
        TrainingExample(
            input_text=f"Classify this task: example {i}",
            expected_output=VALID_TOOLSETS[i % len(VALID_TOOLSETS)],
            task_type=TASK_TYPE,
            metadata={"session_id": f"sess-{i}", "success": 1},
        )
        for i in range(50)
    ]


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for compiled programs."""
    return tmp_path / "distilled"


class TestToolsetClassifier:
    """Test DSPy program definition."""

    def test_signature_has_correct_input_field(self) -> None:
        classifier = ToolsetClassifier()
        sig = classifier.predict.predict.signature
        # input_fields is a pydantic-generated attribute, invisible to pyright
        assert "input_message" in sig.input_fields  # pyright: ignore[reportAttributeAccessIssue]

    def test_signature_has_correct_output_field(self) -> None:
        classifier = ToolsetClassifier()
        sig = classifier.predict.predict.signature
        # output_fields is a pydantic-generated attribute, invisible to pyright
        assert "toolset_name" in sig.output_fields  # pyright: ignore[reportAttributeAccessIssue]

    def test_module_is_dspy_module(self) -> None:
        classifier = ToolsetClassifier()
        assert isinstance(classifier, dspy.Module)

    def test_forward_calls_predict(self) -> None:
        classifier = ToolsetClassifier()
        mock_predict = MagicMock()
        mock_predict.return_value = dspy.Prediction(toolset_name="search_rag")
        classifier.predict = mock_predict

        result = classifier.forward(input_message="test input")

        mock_predict.assert_called_once_with(input_message="test input")
        assert result.toolset_name == "search_rag"


class TestToolsetMatchMetric:
    """Test the _toolset_match_metric function."""

    def test_matching_toolset_names(self) -> None:
        example = dspy.Example(toolset_name="search_rag")
        prediction = dspy.Prediction(toolset_name="search_rag")
        assert _toolset_match_metric(example, prediction) is True

    def test_non_matching_toolset_names(self) -> None:
        example = dspy.Example(toolset_name="search_rag")
        prediction = dspy.Prediction(toolset_name="code_gen")
        assert _toolset_match_metric(example, prediction) is False

    def test_matching_with_whitespace(self) -> None:
        example = dspy.Example(toolset_name="  search_rag  ")
        prediction = dspy.Prediction(toolset_name="search_rag")
        assert _toolset_match_metric(example, prediction) is True


class TestCompilation:
    """Test compilation with mock LMs."""

    @patch("augments.distillation.compiler.dspy")
    def test_compile_returns_compilation_result(
        self,
        mock_dspy: MagicMock,
        train_examples: list[TrainingExample],
        output_dir: Path,
    ) -> None:
        # Set up mock bootstrap optimizer
        mock_optimizer = MagicMock()
        mock_compiled = MagicMock(spec=dspy.Module)
        mock_compiled.save = MagicMock()
        mock_optimizer.compile.return_value = mock_compiled
        mock_dspy.BootstrapFewShot.return_value = mock_optimizer
        mock_dspy.LM.return_value = MagicMock()
        mock_dspy.Example = dspy.Example
        mock_dspy.settings.configure = MagicMock()

        result = compile_program(
            train_examples=train_examples,
            task_type=TASK_TYPE,
            output_dir=output_dir,
        )

        assert isinstance(result, CompilationResult)
        assert result.task_type == TASK_TYPE
        assert result.num_examples == 50
        assert result.duration_seconds >= 0

    @patch("augments.distillation.compiler.dspy")
    def test_compile_configures_teacher_and_student(
        self,
        mock_dspy: MagicMock,
        train_examples: list[TrainingExample],
        output_dir: Path,
    ) -> None:
        mock_optimizer = MagicMock()
        mock_compiled = MagicMock(spec=dspy.Module)
        mock_compiled.save = MagicMock()
        mock_optimizer.compile.return_value = mock_compiled
        mock_dspy.BootstrapFewShot.return_value = mock_optimizer
        mock_dspy.LM.return_value = MagicMock()
        mock_dspy.Example = dspy.Example
        mock_dspy.settings.configure = MagicMock()

        compile_program(
            train_examples=train_examples,
            task_type=TASK_TYPE,
            teacher_model="gpt-5.4-mini",
            student_model="qwen3.5:9b",
            output_dir=output_dir,
        )

        # Teacher LM should be configured with OpenAI
        lm_calls = mock_dspy.LM.call_args_list
        assert len(lm_calls) >= 2
        teacher_kwargs = lm_calls[0].kwargs
        student_kwargs = lm_calls[1].kwargs
        assert teacher_kwargs["model"] == "openai/gpt-5.4-mini"
        assert teacher_kwargs["api_base"] == "http://127.0.0.1:11436/v1"
        assert teacher_kwargs["api_key"] == "vizier-local-gateway"
        assert teacher_kwargs["headers"]["x-vizier-source"] == "distillation"
        assert teacher_kwargs["headers"]["x-vizier-step-name"] == "teacher_bootstrap"
        assert student_kwargs["model"] == "openai/qwen3.5:9b"
        assert student_kwargs["api_base"] == "http://127.0.0.1:11436/v1"
        assert student_kwargs["api_key"] == "vizier-local-gateway"
        assert student_kwargs["headers"]["x-vizier-step-name"] == "student_compile"

    @patch("augments.distillation.compiler.dspy")
    def test_compile_saves_program(
        self,
        mock_dspy: MagicMock,
        train_examples: list[TrainingExample],
        output_dir: Path,
    ) -> None:
        mock_optimizer = MagicMock()
        mock_compiled = MagicMock(spec=dspy.Module)
        mock_compiled.save = MagicMock()
        mock_optimizer.compile.return_value = mock_compiled
        mock_dspy.BootstrapFewShot.return_value = mock_optimizer
        mock_dspy.LM.return_value = MagicMock()
        mock_dspy.Example = dspy.Example
        mock_dspy.settings.configure = MagicMock()

        result = compile_program(
            train_examples=train_examples,
            task_type=TASK_TYPE,
            output_dir=output_dir,
        )

        mock_compiled.save.assert_called_once()
        assert result.program_path == output_dir / TASK_TYPE / "program.json"


class TestProgramSerialization:
    """Test program save/load round-trip."""

    def test_save_and_load(self, output_dir: Path) -> None:
        program = ToolsetClassifier()
        save_path = output_dir / TASK_TYPE
        save_path.mkdir(parents=True, exist_ok=True)
        program.save(str(save_path / "program.json"))

        loaded = load_program(save_path / "program.json")
        assert isinstance(loaded, ToolsetClassifier)

    def test_load_nonexistent_raises(self, output_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_program(output_dir / "nonexistent" / "program.json")


class TestCompilationResultFields:
    """Test CompilationResult dataclass fields."""

    def test_all_fields_present(self) -> None:
        result = CompilationResult(
            task_type=TASK_TYPE,
            num_examples=200,
            num_bootstrapped=4,
            duration_seconds=12.5,
            program_path=Path("data/distilled/task_classification/program.json"),
        )
        assert result.task_type == TASK_TYPE
        assert result.num_examples == 200
        assert result.num_bootstrapped == 4
        assert result.duration_seconds == 12.5
        assert result.program_path == Path(
            "data/distilled/task_classification/program.json"
        )


class TestDistillationGatewayConfig:
    def test_distillation_gateway_base_url_uses_env_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:19999/v1")

        assert distillation_gateway_base_url() == "http://127.0.0.1:19999/v1"

    @patch("augments.distillation.compiler.dspy")
    def test_build_distillation_lm_stamps_gateway_headers(
        self,
        mock_dspy: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_dspy.LM.return_value = MagicMock()
        monkeypatch.setenv("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:15555/v1")

        build_distillation_lm(
            model_name="qwen3.5:9b",
            step_name="student_evaluate",
            temperature=0.0,
        )

        call_kwargs = mock_dspy.LM.call_args.kwargs
        assert call_kwargs["model"] == "openai/qwen3.5:9b"
        assert call_kwargs["api_base"] == "http://127.0.0.1:15555/v1"
        assert call_kwargs["api_key"] == "vizier-local-gateway"
        assert call_kwargs["headers"]["x-vizier-source"] == "distillation"
        assert call_kwargs["headers"]["x-vizier-pipeline-name"] == "distillation"
        assert call_kwargs["headers"]["x-vizier-pipeline-version"] == "1.0"
        assert call_kwargs["headers"]["x-vizier-step-name"] == "student_evaluate"
