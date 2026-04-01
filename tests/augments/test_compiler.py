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
    compile_program,
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
        teacher_call = lm_calls[0]
        student_call = lm_calls[1]
        assert "gpt-5.4-mini" in str(teacher_call)
        assert "qwen3.5:9b" in str(student_call)

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
