"""Watch uploads/ directory for new files, classify, and start Hermes sessions.

Polls uploads/ every 30 seconds. On new file:
1. Validate format (CSV, JSON, XLSX)
2. Detect schema (column names, types)
3. Classify by filename convention (config/triggers/filename_rules.yaml)
4. Fallback: return fallback toolset
5. Start Hermes session with toolset + file path + schema as prompt
6. Move processed file to uploads/_processed/{timestamp}_{filename}
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)

_ACCEPTED_EXTENSIONS = frozenset({".csv", ".json", ".xlsx"})
_XLSX_MAGIC = b"PK\x03\x04"
_CSV_SNIFF_BYTES = 8192
_DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "triggers" / "filename_rules.yaml"


@dataclass(frozen=True)
class FileClassification:
    """Result of classifying a file by its filename prefix."""

    toolset: str
    pipeline: str | None
    matched_rule: str | None


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a file's format and content."""

    valid: bool
    format: str | None
    error: str | None


@dataclass(frozen=True)
class ProcessResult:
    """Result of processing a single upload file."""

    status: str  # "processed" or "failed"
    toolset: str
    pipeline: str | None
    schema: dict[str, str]
    error: str | None


def _load_rules(rules_path: Path) -> dict[str, object]:
    """Load filename rules from YAML config."""
    with rules_path.open("r") as fh:
        data: dict[str, object] = yaml.safe_load(fh)
    return data


def classify_file(
    filename: str, *, rules_path: Path | None = None
) -> FileClassification:
    """Classify a file by matching its filename against prefix rules.

    Args:
        filename: The basename of the file to classify.
        rules_path: Path to the YAML rules config. Defaults to
            config/triggers/filename_rules.yaml.

    Returns:
        FileClassification with the matched toolset and pipeline.
    """
    resolved_path = rules_path or _DEFAULT_RULES_PATH
    config = _load_rules(resolved_path)

    rules: list[dict[str, str | None]] = config.get("rules", [])  # type: ignore[assignment]
    for rule in rules:
        prefix = rule.get("prefix", "")
        if prefix and filename.startswith(prefix):  # type: ignore[arg-type]
            return FileClassification(
                toolset=str(rule["toolset"]),
                pipeline=rule.get("pipeline") if rule.get("pipeline") is not None else None,  # type: ignore[arg-type]
                matched_rule=str(prefix),
            )

    fallback: dict[str, str | None] = config.get("fallback", {})  # type: ignore[assignment]
    return FileClassification(
        toolset=str(fallback.get("toolset", "vizier-fallback")),
        pipeline=fallback.get("pipeline") if fallback.get("pipeline") is not None else None,  # type: ignore[arg-type]
        matched_rule=None,
    )


def validate_file(file_path: Path) -> ValidationResult:
    """Validate that a file has an accepted format and is well-formed.

    Accepted extensions: .csv, .json, .xlsx
    - CSV: validated via csv.Sniffer on first 8KB
    - JSON: validated via json.load
    - XLSX: validated via PK zip magic bytes

    Args:
        file_path: Path to the file to validate.

    Returns:
        ValidationResult indicating whether the file is valid.
    """
    suffix = file_path.suffix.lower()

    if suffix not in _ACCEPTED_EXTENSIONS:
        return ValidationResult(
            valid=False,
            format=None,
            error=f"Unsupported extension '{suffix}'. Accepted: {', '.join(sorted(_ACCEPTED_EXTENSIONS))}",
        )

    if not file_path.exists() or file_path.stat().st_size == 0:
        return ValidationResult(
            valid=False,
            format=suffix.lstrip("."),
            error="File is empty or does not exist",
        )

    if suffix == ".csv":
        return _validate_csv(file_path)
    if suffix == ".json":
        return _validate_json(file_path)
    if suffix == ".xlsx":
        return _validate_xlsx(file_path)

    # Unreachable due to extension check, but satisfies type checker
    return ValidationResult(valid=False, format=None, error="Unknown format")  # pragma: no cover


def _validate_csv(file_path: Path) -> ValidationResult:
    """Validate a CSV file using csv.Sniffer."""
    try:
        raw = file_path.read_text(encoding="utf-8")
        if not raw.strip():
            return ValidationResult(valid=False, format="csv", error="CSV file is empty")
        sample = raw[:_CSV_SNIFF_BYTES]
        csv.Sniffer().sniff(sample)
        return ValidationResult(valid=True, format="csv", error=None)
    except csv.Error as exc:
        return ValidationResult(valid=False, format="csv", error=f"CSV validation failed: {exc}")
    except (UnicodeDecodeError, ValueError) as exc:
        return ValidationResult(valid=False, format="csv", error=f"CSV file is not valid UTF-8: {exc}")


def _validate_json(file_path: Path) -> ValidationResult:
    """Validate a JSON file by parsing it."""
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            json.load(fh)
        return ValidationResult(valid=True, format="json", error=None)
    except (json.JSONDecodeError, ValueError) as exc:
        return ValidationResult(valid=False, format="json", error=f"JSON validation failed: {exc}")


def _validate_xlsx(file_path: Path) -> ValidationResult:
    """Validate an XLSX file by checking PK zip magic bytes."""
    header = file_path.read_bytes()[:4]
    if header == _XLSX_MAGIC:
        return ValidationResult(valid=True, format="xlsx", error=None)
    return ValidationResult(
        valid=False,
        format="xlsx",
        error="XLSX file does not have valid PK zip header",
    )


def detect_schema(file_path: Path) -> dict[str, str]:
    """Detect the schema (column names and type hints) of a data file.

    Args:
        file_path: Path to the data file (.csv, .json, or .xlsx).

    Returns:
        Dictionary mapping column/field names to type hint strings.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        return _detect_schema_csv(file_path)
    if suffix == ".json":
        return _detect_schema_json(file_path)
    if suffix == ".xlsx":
        return _detect_schema_xlsx(file_path)

    return {}


def _detect_schema_csv(file_path: Path) -> dict[str, str]:
    """Read CSV header row and return {column: 'string'} for each."""
    with file_path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        headers = next(reader, [])
    return {col.strip(): "string" for col in headers if col.strip()}


def _detect_schema_json(file_path: Path) -> dict[str, str]:
    """Read first JSON item's keys."""
    with file_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        return {str(key): type(val).__name__ for key, val in data[0].items()}
    if isinstance(data, dict):
        return {str(key): type(val).__name__ for key, val in data.items()}
    return {}


def _detect_schema_xlsx(file_path: Path) -> dict[str, str]:
    """Read XLSX first row as headers (stub -- no openpyxl dependency)."""
    # Without openpyxl, we cannot parse XLSX content.
    # Return empty schema; the Hermes session will handle schema detection.
    logger.warning("xlsx_schema_detection_limited", path=str(file_path))
    return {}


_HERMES_ENTRY = Path(__file__).resolve().parents[2] / "hermes-agent" / "run_agent.py"
_HERMES_TIMEOUT_SECONDS = 300  # 5 minutes


def _start_hermes_session(
    toolset: str,
    pipeline: str | None,
    file_path: Path,
    schema: dict[str, str],
    *,
    dry_run: bool = False,
) -> None:
    """Start a Hermes agent session with the given toolset and file context.

    Args:
        toolset: The Hermes toolset to enable.
        pipeline: Optional pipeline name for context.
        file_path: Path to the data file being processed.
        schema: Detected schema (column names → types).
        dry_run: If True, log the command instead of executing it.
    """
    prompt_parts = [f"Process file: {file_path.name}"]
    if pipeline:
        prompt_parts.append(f"Pipeline: {pipeline}")
    if schema:
        prompt_parts.append(f"Schema: {json.dumps(schema)}")
    prompt = "\n".join(prompt_parts)

    cmd = [
        "python3",
        str(_HERMES_ENTRY),
        "--query",
        prompt,
        "--enabled_toolsets",
        toolset,
        "--max_turns",
        "10",
    ]

    if dry_run:
        logger.info(
            "hermes_session_dry_run",
            toolset=toolset,
            pipeline=pipeline,
            file_path=str(file_path),
            schema_keys=list(schema.keys()),
            command=cmd,
        )
        return

    # Load .env into subprocess environment
    env = {**os.environ}
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()

    logger.info(
        "hermes_session_starting",
        toolset=toolset,
        pipeline=pipeline,
        file_path=str(file_path),
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=_HERMES_TIMEOUT_SECONDS,
        env=env,
    )

    if result.returncode != 0:
        logger.error(
            "hermes_session_failed",
            returncode=result.returncode,
            stderr=result.stderr[:500],
        )
        msg = f"Hermes session failed (exit {result.returncode}): {result.stderr[:200]}"
        raise RuntimeError(msg)

    logger.info(
        "hermes_session_completed",
        toolset=toolset,
        stdout_preview=result.stdout[:200],
    )


def _move_file(file_path: Path, dest_dir: Path) -> Path:
    """Move a file to a destination directory with timestamp prefix.

    Args:
        file_path: The file to move.
        dest_dir: Target directory (created if needed).

    Returns:
        The new path of the moved file.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"{timestamp}_{file_path.name}"
    shutil.move(str(file_path), str(dest_path))
    return dest_path


def process_file(
    file_path: Path,
    uploads_dir: Path,
    *,
    rules_path: Path | None = None,
    dry_run: bool = True,
) -> ProcessResult:
    """Process a single uploaded file: validate, classify, detect schema, dispatch.

    On success the file is moved to uploads/_processed/{timestamp}_{filename}.
    On failure the file is moved to uploads/_failed/{timestamp}_{filename}.

    Args:
        file_path: Path to the uploaded file.
        uploads_dir: Root uploads directory.
        rules_path: Optional path to filename rules YAML.
        dry_run: If True, log Hermes command instead of executing.

    Returns:
        ProcessResult with status, toolset, pipeline, schema, and any error.
    """
    log = logger.bind(file=str(file_path))

    # Step 1: Validate
    validation = validate_file(file_path)
    if not validation.valid:
        log.warning("file_validation_failed", error=validation.error)
        _move_file(file_path, uploads_dir / "_failed")
        return ProcessResult(
            status="failed",
            toolset="",
            pipeline=None,
            schema={},
            error=validation.error,
        )

    # Step 2: Classify
    classification = classify_file(file_path.name, rules_path=rules_path)
    log.info("file_classified", toolset=classification.toolset, pipeline=classification.pipeline)

    # Step 3: Detect schema
    schema = detect_schema(file_path)
    log.info("schema_detected", columns=list(schema.keys()))

    # Step 4: Start Hermes session
    try:
        _start_hermes_session(
            toolset=classification.toolset,
            pipeline=classification.pipeline,
            file_path=file_path,
            schema=schema,
            dry_run=dry_run,
        )
    except Exception as exc:
        log.error("hermes_session_failed", error=str(exc))
        _move_file(file_path, uploads_dir / "_failed")
        return ProcessResult(
            status="failed",
            toolset=classification.toolset,
            pipeline=classification.pipeline,
            schema=schema,
            error=f"Hermes session failed: {exc}",
        )

    # Step 5: Move to _processed
    _move_file(file_path, uploads_dir / "_processed")
    log.info("file_processed_successfully")

    return ProcessResult(
        status="processed",
        toolset=classification.toolset,
        pipeline=classification.pipeline,
        schema=schema,
        error=None,
    )


def poll_uploads(
    uploads_dir: Path,
    interval: float = 30.0,
    *,
    rules_path: Path | None = None,
) -> None:
    """Poll uploads directory for new files and process them.

    Runs forever until KeyboardInterrupt. Skips _processed/ and _failed/
    subdirectories.

    Args:
        uploads_dir: Root uploads directory to watch.
        interval: Seconds between poll cycles.
        rules_path: Optional path to filename rules YAML.
    """
    log = logger.bind(uploads_dir=str(uploads_dir))
    log.info("poll_started", interval=interval)

    skip_dirs = {"_processed", "_failed"}

    try:
        while True:
            if uploads_dir.exists():
                for item in uploads_dir.iterdir():
                    if item.is_dir() and item.name in skip_dirs:
                        continue
                    if item.is_file():
                        log.info("new_file_detected", file=item.name)
                        process_file(item, uploads_dir, rules_path=rules_path)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("poll_stopped")
