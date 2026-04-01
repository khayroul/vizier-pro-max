"""DSPy program definition + compilation from GPT-5.4-mini teacher to Qwen student.

Defines a DSPy Signature (message -> toolset) and uses BootstrapFewShot
to optimize prompts for Qwen 3.5 9B via Ollama.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import dspy
import structlog

from augments.distillation.collector import TrainingExample

log = structlog.get_logger(__name__)

DEFAULT_OUTPUT_DIR = Path("data/distilled")
DEFAULT_TEACHER_MODEL = "gpt-5.4-mini"
DEFAULT_STUDENT_MODEL = "qwen3.5:9b"
OLLAMA_BASE_URL = "http://localhost:11434"


@dataclass(frozen=True)
class CompilationResult:
    """Result of compiling a DSPy program."""

    task_type: str
    num_examples: int
    num_bootstrapped: int
    duration_seconds: float
    program_path: Path


class ToolsetSignature(dspy.Signature):
    """Classify an input message to determine the appropriate toolset."""

    input_message: str = dspy.InputField(desc="The user input message to classify")
    toolset_name: str = dspy.OutputField(desc="The name of the toolset to use")


class ToolsetClassifier(dspy.Module):
    """DSPy module wrapping ToolsetSignature with Chain-of-Thought reasoning."""

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(ToolsetSignature)

    def forward(self, input_message: str) -> dspy.Prediction:
        """Run the classifier on an input message.

        Args:
            input_message: The message to classify.

        Returns:
            DSPy Prediction with toolset_name field.
        """
        return self.predict(input_message=input_message)


def _examples_to_dspy(examples: list[TrainingExample]) -> list[dspy.Example]:
    """Convert TrainingExample list to DSPy Example list."""
    return [
        dspy.Example(
            input_message=ex.input_text,
            toolset_name=ex.expected_output,
        ).with_inputs("input_message")
        for ex in examples
    ]


def _toolset_match_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace: object = None,
) -> bool:
    """Check if the predicted toolset matches the expected one.

    Args:
        example: The ground truth example.
        prediction: The model prediction.
        trace: Optional trace info (unused, required by DSPy API).

    Returns:
        True if toolset_name matches.
    """
    return str(example.toolset_name).strip() == str(prediction.toolset_name).strip()


def compile_program(
    train_examples: list[TrainingExample],
    task_type: str,
    teacher_model: str = DEFAULT_TEACHER_MODEL,
    student_model: str = DEFAULT_STUDENT_MODEL,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> CompilationResult:
    """Compile a DSPy program using BootstrapFewShot from teacher to student.

    Args:
        train_examples: Training examples to bootstrap from.
        task_type: The task type being compiled.
        teacher_model: Teacher model name (OpenAI).
        student_model: Student model name (Ollama).
        output_dir: Directory to save the compiled program.

    Returns:
        CompilationResult with compilation metadata.
    """
    log.info(
        "compiling_program",
        task_type=task_type,
        num_examples=len(train_examples),
        teacher=teacher_model,
        student=student_model,
    )

    start_time = time.monotonic()

    # Configure LMs
    teacher_lm = dspy.LM(
        model=f"openai/{teacher_model}",
        temperature=0.7,
    )
    student_lm = dspy.LM(
        model=f"ollama_chat/{student_model}",
        api_base=OLLAMA_BASE_URL,
        temperature=0.0,
    )

    # Configure DSPy to use the student as default, teacher for bootstrapping
    dspy.settings.configure(lm=student_lm)

    # Convert examples
    dspy_examples = _examples_to_dspy(train_examples)

    # Create optimizer
    optimizer = dspy.BootstrapFewShot(
        metric=_toolset_match_metric,
        max_bootstrapped_demos=4,
        max_labeled_demos=16,
        max_rounds=1,
        teacher_settings={"lm": teacher_lm},
    )

    # Compile
    program = ToolsetClassifier()
    compiled_program = optimizer.compile(program, trainset=dspy_examples)

    # Save
    program_dir = output_dir / task_type
    program_dir.mkdir(parents=True, exist_ok=True)
    program_path = program_dir / "program.json"
    compiled_program.save(str(program_path))

    duration = time.monotonic() - start_time

    result = CompilationResult(
        task_type=task_type,
        num_examples=len(train_examples),
        num_bootstrapped=min(4, len(train_examples)),
        duration_seconds=duration,
        program_path=program_path,
    )

    log.info(
        "compilation_complete",
        task_type=task_type,
        duration_seconds=round(duration, 2),
        program_path=str(program_path),
    )

    return result


def load_program(program_path: Path) -> ToolsetClassifier:
    """Load a compiled DSPy program from disk.

    Args:
        program_path: Path to the saved program.json.

    Returns:
        Loaded ToolsetClassifier instance.

    Raises:
        FileNotFoundError: If the program file doesn't exist.
    """
    if not program_path.exists():
        msg = f"Program file not found: {program_path}"
        raise FileNotFoundError(msg)

    program = ToolsetClassifier()
    program.load(str(program_path))
    return program
