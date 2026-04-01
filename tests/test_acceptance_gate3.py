"""Gate 3 known-answer acceptance tests — real execution, no mocks.

Each test feeds the real system a known input where we already know
the correct answer, then checks if the output matches. If these pass,
the wiring works end-to-end.

Run with: pytest tests/test_acceptance_gate3.py -v --tb=short
"""
from __future__ import annotations

import json
import sqlite3
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Acceptance 1: Synthetic generator → Collector round-trip
#
# "If I generate synthetic data and then collect it, do I get back
#  the right task types with the right counts?"
# ---------------------------------------------------------------------------


class TestSyntheticToCollector:
    """Generate synthetic data, then verify the collector reads it correctly."""

    def test_generate_then_collect_task_classification(self, tmp_path: Path) -> None:
        """Generate 200 synthetic rows, collect task_classification, verify split."""
        from scripts.bootstrap.generate_synthetic_sessions import (
            generate_synthetic_sessions,
        )

        config_path = Path("config/bootstrap/synthetic_sessions.yaml")
        db_path = tmp_path / "prompt_log.db"

        count = generate_synthetic_sessions(config_path, db_path, seed=42)
        assert count == 200

        from augments.distillation.collector import collect

        result = collect("task_classification", db_path=db_path, seed=42)

        # Known answer: 80 task_classification rows, 80% train / 20% test
        assert result.total_count == 80
        assert len(result.train_set) == 64  # 80 * 0.8
        assert len(result.test_set) == 16  # 80 * 0.2

        # Every example should have expected_output == "classifier"
        for example in result.train_set + result.test_set:
            assert example.expected_output == "classifier"
            assert example.task_type == "task_classification"

    def test_collect_all_four_task_types(self, tmp_path: Path) -> None:
        """All 4 task types are present with correct toolset assignments."""
        from scripts.bootstrap.generate_synthetic_sessions import (
            generate_synthetic_sessions,
        )

        config_path = Path("config/bootstrap/synthetic_sessions.yaml")
        db_path = tmp_path / "prompt_log.db"
        generate_synthetic_sessions(config_path, db_path, seed=42)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT task_type, toolset_chosen, COUNT(*) "
            "FROM training_sessions GROUP BY task_type, toolset_chosen"
        ).fetchall()
        conn.close()

        result_map = {row[0]: (row[1], row[2]) for row in rows}

        # Known answers from synthetic_sessions.yaml
        assert result_map["task_classification"] == ("classifier", 80)
        assert result_map["template_selection"] == ("template_selector", 50)
        assert result_map["tool_routing"] == ("router", 40)
        assert result_map["outline_generation"] == ("outliner", 30)

    def test_deterministic_across_runs(self, tmp_path: Path) -> None:
        """Same seed → identical data both times."""
        from scripts.bootstrap.generate_synthetic_sessions import (
            generate_synthetic_sessions,
        )

        config = Path("config/bootstrap/synthetic_sessions.yaml")
        db1 = tmp_path / "run1.db"
        db2 = tmp_path / "run2.db"

        generate_synthetic_sessions(config, db1, seed=99)
        generate_synthetic_sessions(config, db2, seed=99)

        conn1 = sqlite3.connect(db1)
        conn2 = sqlite3.connect(db2)
        rows1 = conn1.execute(
            "SELECT input_message FROM training_sessions ORDER BY session_id"
        ).fetchall()
        rows2 = conn2.execute(
            "SELECT input_message FROM training_sessions ORDER BY session_id"
        ).fetchall()
        conn1.close()
        conn2.close()

        assert rows1 == rows2


# ---------------------------------------------------------------------------
# Acceptance 2: Sandbox guard — known-dangerous and known-safe code
#
# "I know exactly which code should be blocked and which should pass.
#  Does the guard agree?"
# ---------------------------------------------------------------------------


class TestSandboxGuardKnownAnswers:
    """Feed the real AST guard known code snippets, check verdicts."""

    @pytest.mark.parametrize(
        "code,should_block,reason",
        [
            # --- Known dangerous ---
            ("import subprocess", True, "subprocess import"),
            ("from subprocess import run", True, "subprocess from-import"),
            ("import openai", True, "direct openai import"),
            ("import anthropic", True, "direct anthropic import"),
            ("eval('1+1')", True, "eval call"),
            ("exec('x=1')", True, "exec call"),
            ("__import__('os')", True, "__import__ call"),
            ("import os\nos.system('ls')", True, "os.system"),
            ("import os\nos.popen('ls')", True, "os.popen"),
            ("import socket", True, "raw socket"),
            ("open('/etc/passwd', 'r')", True, "read outside allowed dirs"),
            ("open('/home/user/.env', 'r')", True, "read dotenv"),
            ("import importlib", True, "importlib import"),
            # --- Known safe ---
            ("x = 1 + 2", False, "arithmetic"),
            ("import json\njson.dumps({'a': 1})", False, "json import"),
            ("import math\nmath.sqrt(4)", False, "math import"),
            ("from pathlib import Path", False, "pathlib import"),
            ("open('output/report.pdf', 'wb')", False, "write to output/"),
            ("open('tmp/scratch.txt', 'w')", False, "write to tmp/"),
            ("data = [i**2 for i in range(10)]", False, "list comprehension"),
            ("print('hello world')", False, "print statement"),
        ],
        ids=lambda x: x if isinstance(x, str) and len(x) < 40 else "",
    )
    def test_guard_verdict(self, code: str, should_block: bool, reason: str) -> None:
        from augments.sandbox.guard import check

        result = check(code)
        assert result.allowed != should_block, (
            f"Expected {'BLOCKED' if should_block else 'ALLOWED'} for: {reason}\n"
            f"Code: {code}\n"
            f"Guard said: allowed={result.allowed}, patterns={result.blocked_patterns}"
        )

    def test_real_pipeline_code_passes_guard(self) -> None:
        """A realistic self-built pipeline should pass the guard."""
        from augments.sandbox.guard import check

        pipeline_code = textwrap.dedent("""\
            import json
            from pathlib import Path

            def run(brief: str, output_dir: str = "output/") -> dict:
                result = {"headline": brief.upper(), "body": f"Content for: {brief}"}
                out_path = Path(output_dir) / "draft.json"
                with open(f"output/{out_path.name}", "w") as fh:
                    json.dump(result, fh)
                return {"status": "done", "path": str(out_path)}
        """)
        result = check(pipeline_code)
        assert result.allowed is True, (
            f"Realistic pipeline blocked: {result.blocked_patterns}"
        )

    def test_malicious_pipeline_blocked(self) -> None:
        """A pipeline that sneaks in openai should be caught."""
        from augments.sandbox.guard import check

        bad_pipeline = textwrap.dedent("""\
            import json
            import openai

            def run(brief: str) -> dict:
                client = openai.Client()
                resp = client.chat.completions.create(
                    model="gpt-4", messages=[{"role": "user", "content": brief}]
                )
                return {"result": resp.choices[0].message.content}
        """)
        result = check(bad_pipeline)
        assert result.allowed is False
        assert any("openai" in p for p in result.blocked_patterns)


# ---------------------------------------------------------------------------
# Acceptance 3: File trigger classification — known filename→toolset map
#
# "Given these exact filenames, do I get the exact toolsets I expect?"
# ---------------------------------------------------------------------------


class TestTriggerClassificationKnownAnswers:
    """Test file classification against known filename→toolset mapping."""

    KNOWN_MAPPINGS = [
        ("posters_march_2026.csv", "vizier-visual", "poster_batch", "posters_"),
        ("posters_q1.csv", "vizier-visual", "poster_batch", "posters_"),
        ("invoices_march.csv", "vizier-document", None, "invoices_"),
        ("invoices_2026_q1.xlsx", "vizier-document", None, "invoices_"),
        ("content_calendar_april.csv", "vizier-content", "content_generate", "content_calendar_"),
        ("content_calendar_weekly.json", "vizier-content", "content_generate", "content_calendar_"),
        ("analysis_competitor_q2.csv", "vizier-research", "competitive_analysis", "analysis_"),
        # Unknowns → fallback
        ("random_data.csv", "vizier-fallback", None, None),
        ("my_spreadsheet.xlsx", "vizier-fallback", None, None),
        ("budget_2026.json", "vizier-fallback", None, None),
    ]

    @pytest.mark.parametrize(
        "filename,expected_toolset,expected_pipeline,expected_rule",
        KNOWN_MAPPINGS,
        ids=[m[0] for m in KNOWN_MAPPINGS],
    )
    def test_classification(
        self,
        filename: str,
        expected_toolset: str,
        expected_pipeline: str | None,
        expected_rule: str | None,
    ) -> None:
        from scripts.triggers.data_trigger import classify_file

        result = classify_file(filename)
        assert result.toolset == expected_toolset, (
            f"{filename}: expected toolset={expected_toolset}, got {result.toolset}"
        )
        assert result.pipeline == expected_pipeline, (
            f"{filename}: expected pipeline={expected_pipeline}, got {result.pipeline}"
        )
        assert result.matched_rule == expected_rule, (
            f"{filename}: expected rule={expected_rule}, got {result.matched_rule}"
        )


# ---------------------------------------------------------------------------
# Acceptance 4: File validation — known good/bad files
#
# "Given these exact file contents, do I get the exact pass/fail I expect?"
# ---------------------------------------------------------------------------


class TestFileValidationKnownAnswers:
    """Test file validation against known good and bad inputs."""

    def test_valid_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "good.csv"
        csv_file.write_text("name,email,amount\nAlice,a@b.com,100\nBob,b@c.com,200\n")

        from scripts.triggers.data_trigger import validate_file

        result = validate_file(csv_file)
        assert result.valid is True
        assert result.format == "csv"

    def test_valid_json(self, tmp_path: Path) -> None:
        json_file = tmp_path / "good.json"
        json_file.write_text(json.dumps([
            {"title": "Spring Poster", "size": "1080x1080"},
            {"title": "Summer Poster", "size": "1920x1080"},
        ]))

        from scripts.triggers.data_trigger import validate_file

        result = validate_file(json_file)
        assert result.valid is True
        assert result.format == "json"

    def test_corrupt_csv(self, tmp_path: Path) -> None:
        bad_csv = tmp_path / "corrupt.csv"
        bad_csv.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")

        from scripts.triggers.data_trigger import validate_file

        result = validate_file(bad_csv)
        assert result.valid is False

    def test_wrong_extension(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("just some notes")

        from scripts.triggers.data_trigger import validate_file

        result = validate_file(txt_file)
        assert result.valid is False

    def test_schema_detection_csv(self, tmp_path: Path) -> None:
        """CSV schema should return exact column names."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("title,color,width,height\nPoster A,red,1080,1080\n")

        from scripts.triggers.data_trigger import detect_schema

        schema = detect_schema(csv_file)
        assert schema == {
            "title": "string",
            "color": "string",
            "width": "string",
            "height": "string",
        }

    def test_schema_detection_json(self, tmp_path: Path) -> None:
        """JSON schema should return keys with Python type names."""
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps([
            {"id": 1, "name": "Alice", "active": True, "score": 9.5},
        ]))

        from scripts.triggers.data_trigger import detect_schema

        schema = detect_schema(json_file)
        assert schema == {"id": "int", "name": "str", "active": "bool", "score": "float"}


# ---------------------------------------------------------------------------
# Acceptance 5: Tier classification — known artifact types
#
# "Given these exact artifacts, do I get the exact tier I expect?"
# ---------------------------------------------------------------------------


class TestTierClassificationKnownAnswers:
    """Verify tier decisions match known expected outcomes."""

    def test_openspace_pipeline_is_tier_1(self, tmp_path: Path) -> None:
        """A pipeline from OpenSpace capture should auto-promote (Tier 1)."""
        from augments.selfbuild.tier_classifier import classify

        pipeline = tmp_path / "pipelines" / "resize_screenshot.py"
        pipeline.parent.mkdir(parents=True)
        pipeline.write_text("def run(**kwargs): pass\n")

        result = classify(
            artifact_path=pipeline,
            manifest_path=None,
            origin="openspace_captured",
        )
        assert result.tier == 1

    def test_new_atomic_tool_is_tier_2(self, tmp_path: Path) -> None:
        """A new tool with a manifest should require human approval (Tier 2)."""
        from augments.selfbuild.tier_classifier import classify

        script = tmp_path / "scripts" / "visual" / "resize_image.py"
        script.parent.mkdir(parents=True)
        script.write_text("def run(**kwargs): pass\n")

        manifest = tmp_path / "manifests" / "visual" / "resize_image.yaml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("name: resize_image\ntoolset: vizier-visual\n")

        result = classify(
            artifact_path=script,
            manifest_path=manifest,
            origin="model_generated",
        )
        assert result.tier == 2

    def test_delivery_tool_is_tier_2(self, tmp_path: Path) -> None:
        """A tool in the delivery toolset should always be Tier 2."""
        from augments.selfbuild.tier_classifier import classify

        script = tmp_path / "scripts" / "delivery" / "send_whatsapp.py"
        script.parent.mkdir(parents=True)
        script.write_text("def run(**kwargs): pass\n")

        manifest = tmp_path / "manifests" / "delivery" / "send_whatsapp.yaml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("name: send_whatsapp\ntoolset: vizier-delivery\n")

        result = classify(
            artifact_path=script,
            manifest_path=manifest,
            origin="model_generated",
        )
        assert result.tier == 2
        assert any("delivery" in r.lower() for r in result.reasons)


# ---------------------------------------------------------------------------
# Acceptance 6: Deployer threshold enforcement
#
# "90% accuracy deploys, 89% does not — no exceptions."
# ---------------------------------------------------------------------------


class TestDeployerThresholdKnownAnswers:
    """Verify deployer respects the 90% accuracy threshold exactly."""

    def test_90_percent_deploys(self, tmp_path: Path) -> None:
        from augments.distillation.deployer import deploy

        models_yaml = tmp_path / "models.yaml"
        distill_config = tmp_path / "distillation_config.yaml"
        models_yaml.write_text(
            "default_model: gpt-5.4-mini\nfallback_model: qwen3.5:9b\n"
            "offline_mode: false\ndistilled_tasks: {}\n"
        )
        distill_config.write_text(
            "tasks:\n  task_classification:\n    status: compiled\n"
            "    accuracy_threshold: 0.90\n"
        )

        result = deploy(
            task_type="task_classification",
            accuracy=0.90,
            program_path=Path("data/distilled/task_classification/program.json"),
            models_yaml_path=models_yaml,
            distillation_config_path=distill_config,
        )
        assert result.status == "deployed"

    def test_89_percent_rejected(self, tmp_path: Path) -> None:
        from augments.distillation.deployer import deploy

        models_yaml = tmp_path / "models.yaml"
        distill_config = tmp_path / "distillation_config.yaml"
        models_yaml.write_text(
            "default_model: gpt-5.4-mini\nfallback_model: qwen3.5:9b\n"
            "offline_mode: false\ndistilled_tasks: {}\n"
        )
        distill_config.write_text(
            "tasks:\n  task_classification:\n    status: compiled\n"
            "    accuracy_threshold: 0.90\n"
        )

        result = deploy(
            task_type="task_classification",
            accuracy=0.89,
            program_path=Path("data/distilled/task_classification/program.json"),
            models_yaml_path=models_yaml,
            distillation_config_path=distill_config,
        )
        assert result.status == "rejected"

    def test_boundary_value_0899_rejected(self, tmp_path: Path) -> None:
        from augments.distillation.deployer import deploy

        models_yaml = tmp_path / "models.yaml"
        distill_config = tmp_path / "distillation_config.yaml"
        models_yaml.write_text(
            "default_model: gpt-5.4-mini\nfallback_model: qwen3.5:9b\n"
            "offline_mode: false\ndistilled_tasks: {}\n"
        )
        distill_config.write_text(
            "tasks:\n  task_classification:\n    status: compiled\n"
            "    accuracy_threshold: 0.90\n"
        )

        result = deploy(
            task_type="task_classification",
            accuracy=0.8999,
            program_path=Path("data/distilled/task_classification/program.json"),
            models_yaml_path=models_yaml,
            distillation_config_path=distill_config,
        )
        assert result.status == "rejected"


# ---------------------------------------------------------------------------
# Acceptance 7: Full file trigger round-trip
#
# "Drop a CSV in uploads/, process it, verify it ends up in _processed/
#  with the correct classification."
# ---------------------------------------------------------------------------


class TestFileTriggerRoundTrip:
    """End-to-end: real CSV → classify → validate → schema → move."""

    def test_posters_csv_full_flow(self, tmp_path: Path) -> None:
        from scripts.triggers.data_trigger import process_file

        uploads = tmp_path / "uploads"
        uploads.mkdir()

        csv_file = uploads / "posters_spring_2026.csv"
        csv_file.write_text(
            "title,color,width,height\n"
            "Spring Collection,red,1080,1080\n"
            "Summer Promo,blue,1920,1080\n"
        )

        result = process_file(csv_file, uploads)

        # Known answers
        assert result.status == "processed"
        assert result.toolset == "vizier-visual"
        assert result.pipeline == "poster_batch"
        assert result.schema == {
            "title": "string",
            "color": "string",
            "width": "string",
            "height": "string",
        }
        assert result.error is None

        # File should be in _processed/, not in uploads/
        assert not csv_file.exists()
        processed = list((uploads / "_processed").iterdir())
        assert len(processed) == 1
        assert "posters_spring_2026.csv" in processed[0].name

    def test_invalid_file_goes_to_failed(self, tmp_path: Path) -> None:
        from scripts.triggers.data_trigger import process_file

        uploads = tmp_path / "uploads"
        uploads.mkdir()

        bad_file = uploads / "data.txt"
        bad_file.write_text("not a valid format")

        result = process_file(bad_file, uploads)

        assert result.status == "failed"
        assert result.error is not None
        assert not bad_file.exists()
        failed = list((uploads / "_failed").iterdir())
        assert len(failed) == 1


# ---------------------------------------------------------------------------
# Acceptance 8: Audit trail records real execution
#
# "After recording an audit entry, I can read it back with correct fields."
# ---------------------------------------------------------------------------


class TestAuditTrailKnownAnswers:
    """Verify audit records contain exactly what we put in."""

    def test_audit_round_trip(self, tmp_path: Path) -> None:
        from augments.sandbox.audit import record

        db_path = tmp_path / "audit.db"
        code = "x = 1 + 2\nprint(x)"

        record(
            code=code,
            exit_code=0,
            duration_ms=42.5,
            files_touched=["output/result.json"],
            db_path=db_path,
        )

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM code_audit").fetchall()
        conn.close()

        assert len(rows) == 1
        row = rows[0]

        # Verify known fields
        import hashlib

        expected_hash = hashlib.sha256(code.encode()).hexdigest()
        # Row structure: id, timestamp, code_hash, code_preview, exit_code,
        #                duration_ms, files_touched_json
        assert row[2] == expected_hash  # code_hash
        assert row[3] == code  # code_preview (under 500 chars)
        assert row[4] == 0  # exit_code
        assert row[5] == 42.5  # duration_ms
        assert json.loads(row[6]) == ["output/result.json"]  # files_touched
