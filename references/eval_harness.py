"""Evaluation helpers for reference-corpus quality measurement."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_ROOT = REPO_ROOT / "evaluations" / "reference_corpus"
SCORE_MIN = 1
SCORE_MAX = 5
POSTER_MANUAL_DIMENSIONS = (
    "composition_choice",
    "hero_prominence",
    "hierarchy_readability",
    "cta_emphasis",
    "copy_sharpness",
    "visual_polish",
    "reference_utilization",
)
_LOOKUP_RUNNER_CODE = """
from __future__ import annotations
import json
import sys

from references.query import (
    search_chart_patterns,
    search_quarto_layouts,
    search_report_layouts,
    search_ui_styles,
    search_ux_guidelines,
)

_TOOLS = {
    "search_ui_styles": search_ui_styles,
    "search_ux_guidelines": search_ux_guidelines,
    "search_chart_patterns": search_chart_patterns,
    "search_report_layouts": search_report_layouts,
    "search_quarto_layouts": search_quarto_layouts,
}

payload = json.load(sys.stdin)
results = []
for case in payload["cases"]:
    tool_name = case["tool"]
    query = case["query"]
    top_k = int(case.get("top_k", 5))
    output = _TOOLS[tool_name](query, top_k=top_k)
    results.append(
        {
            "prompt_id": case["prompt_id"],
            "tool": tool_name,
            "query": query,
            "results": output,
        }
    )

json.dump({"results": results}, sys.stdout)
"""
_POSTER_RUNNER_CODE = """
from __future__ import annotations
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFilter

import pipelines.poster_brief as poster_brief
import pipelines.poster_generate as poster_generate


CURRENT_CASE: dict[str, object] = {}


def _mix(color_a: str, color_b: str, ratio: float) -> tuple[int, int, int]:
    a = ImageColor.getrgb(color_a)
    b = ImageColor.getrgb(color_b)
    return tuple(
        max(0, min(255, round((channel_a * (1.0 - ratio)) + (channel_b * ratio))))
        for channel_a, channel_b in zip(a, b)
    )


def _fixture_alignment(case_id: str) -> str:
    lowered = case_id.lower()
    if "swiss" in lowered or "analytics" in lowered:
        return "left"
    if "retro" in lowered or "event" in lowered:
        return "center"
    if "donation" in lowered or "trust" in lowered:
        return "upper"
    return "center"


def _write_fixture_hero(case_id: str, palette: dict[str, str], output_path: str) -> str:
    width = 1024
    height = 1024
    background = palette.get("background", "#111111")
    secondary = palette.get("secondary", background)
    accent = palette.get("accent", palette.get("primary", "#d1a054"))
    foreground = palette.get("text", "#ffffff")
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        row_color = _mix(background, secondary, ratio * 0.75)
        draw.line([(0, y), (width, y)], fill=row_color, width=1)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    alignment = _fixture_alignment(case_id)
    center_x = {"left": width * 0.34, "upper": width * 0.5, "center": width * 0.5}[alignment]
    center_y = {"left": height * 0.45, "upper": height * 0.28, "center": height * 0.42}[alignment]
    radius_x = 240 if alignment == "upper" else 280
    radius_y = 200 if alignment == "upper" else 250
    overlay_draw.ellipse(
        (
            center_x - radius_x,
            center_y - radius_y,
            center_x + radius_x,
            center_y + radius_y,
        ),
        fill=ImageColor.getrgb(accent) + (190,),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=42))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)

    accent_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent_overlay)
    if alignment == "left":
        accent_draw.rounded_rectangle(
            (130, 190, 620, 720),
            radius=36,
            outline=ImageColor.getrgb(foreground) + (90,),
            width=8,
            fill=(255, 255, 255, 18),
        )
        for offset in range(0, 360, 60):
            accent_draw.line(
                (150, 250 + offset, 600, 250 + offset),
                fill=ImageColor.getrgb(foreground) + (45,),
                width=4,
            )
    elif alignment == "upper":
        accent_draw.polygon(
            [(512, 140), (720, 340), (620, 640), (404, 740), (280, 360)],
            fill=ImageColor.getrgb(accent) + (110,),
        )
    else:
        accent_draw.rectangle(
            (360, 200, 664, 760),
            fill=ImageColor.getrgb(foreground) + (28,),
            outline=ImageColor.getrgb(accent) + (110,),
            width=10,
        )
    image = Image.alpha_composite(image, accent_overlay)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(out)
    return str(out)


def _fake_generate_hero(prompt: str, output_path: str, mode: str) -> str:
    inputs = dict(CURRENT_CASE.get("poster_inputs") or {})
    palette = dict(inputs.get("palette") or {})
    return _write_fixture_hero(str(CURRENT_CASE["prompt_id"]), palette, output_path)


def _fake_llm_chat(*args: object, **kwargs: object) -> str:
    response = CURRENT_CASE.get("mock_brief_response")
    if response is None:
        return ""
    return json.dumps(response, ensure_ascii=False)


payload = json.load(sys.stdin)
poster_generate._generate_hero = _fake_generate_hero
poster_brief.llm_chat = _fake_llm_chat

results = []
for case in payload["cases"]:
    CURRENT_CASE = case
    inputs = dict(case["poster_inputs"])
    output_dir = Path(payload["output_root"]) / str(case["prompt_id"])
    output_path = output_dir / "poster.png"
    inputs["output_path"] = str(output_path)
    result = poster_generate.run(**inputs)
    results.append(
        {
            "prompt_id": case["prompt_id"],
            "result": result,
        }
    )

json.dump({"results": results}, sys.stdout)
"""


@dataclass(frozen=True)
class LookupProbeSpec:
    """Deterministic lookup probe associated with one frozen prompt."""

    tool: str
    query: str
    top_k: int
    required_patterns: tuple[str, ...]
    preferred_top_patterns: tuple[str, ...]


@dataclass(frozen=True)
class EvalPrompt:
    """Frozen prompt plus lookup expectations and scoring focus."""

    prompt_id: str
    family: str
    title: str
    suggested_pipeline: str
    artifact_prompt: str
    output_expectation: str
    expected_quality_boosts: tuple[str, ...]
    dimension_weights: dict[str, float]
    lookup_probe: LookupProbeSpec
    notes: str = ""


@dataclass(frozen=True)
class RubricDimension:
    """Single rubric dimension with scoring guidance."""

    dimension_id: str
    label: str
    description: str
    anchors: dict[int, str]


@dataclass(frozen=True)
class MilestoneSpec:
    """Git milestone to compare during evaluation."""

    milestone_id: str
    label: str
    git_ref: str
    description: str


@dataclass(frozen=True)
class PosterArtifactCase:
    """Frozen artifact-run case for poster/UI evaluation."""

    prompt_id: str
    family: str
    title: str
    prompt: str
    poster_inputs: dict[str, Any]
    mock_brief_response: dict[str, Any] | None
    expected_reference_tools: tuple[str, ...]
    preferred_templates: tuple[str, ...]
    discouraged_templates: tuple[str, ...]
    required_prompt_terms: tuple[str, ...]
    manual_focus: tuple[str, ...]


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Expected mapping at {path}"
        raise ValueError(msg)
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_rubric_dimensions(path: Path) -> dict[str, RubricDimension]:
    payload = _read_yaml(path)
    dimensions = payload.get("dimensions", [])
    rubric: dict[str, RubricDimension] = {}
    for raw in dimensions:
        if not isinstance(raw, dict):
            msg = "Rubric dimensions must be mappings"
            raise ValueError(msg)
        anchors = raw.get("anchors", {})
        rubric[str(raw["id"])] = RubricDimension(
            dimension_id=str(raw["id"]),
            label=str(raw["label"]),
            description=str(raw["description"]),
            anchors={int(key): str(value) for key, value in anchors.items()},
        )
    if not rubric:
        msg = "Rubric must contain at least one dimension"
        raise ValueError(msg)
    return rubric


def load_rubric(eval_root: Path = EVAL_ROOT) -> dict[str, RubricDimension]:
    """Load rubric dimensions keyed by dimension id."""
    return _load_rubric_dimensions(eval_root / "rubric.yaml")


def _validate_dimension_weights(
    prompt_id: str,
    dimension_weights: dict[str, float],
    rubric: dict[str, RubricDimension],
) -> None:
    if not dimension_weights:
        msg = f"Prompt {prompt_id} must define dimension_weights"
        raise ValueError(msg)
    unknown = sorted(set(dimension_weights) - set(rubric))
    if unknown:
        msg = f"Prompt {prompt_id} references unknown dimensions: {unknown}"
        raise ValueError(msg)
    total = round(sum(dimension_weights.values()), 6)
    if abs(total - 1.0) > 0.001:
        msg = f"Prompt {prompt_id} weights must sum to 1.0, got {total}"
        raise ValueError(msg)


def load_prompt_suite(eval_root: Path = EVAL_ROOT) -> list[EvalPrompt]:
    """Load the frozen prompt suite."""
    payload = _read_yaml(eval_root / "suite.yaml")
    raw_prompts = payload.get("prompts", [])
    if not isinstance(raw_prompts, list) or not raw_prompts:
        msg = "Prompt suite must contain prompts"
        raise ValueError(msg)
    rubric = load_rubric(eval_root)
    prompts: list[EvalPrompt] = []
    seen_ids: set[str] = set()
    for raw in raw_prompts:
        if not isinstance(raw, dict):
            msg = "Prompt entries must be mappings"
            raise ValueError(msg)
        prompt_id = str(raw["id"])
        if prompt_id in seen_ids:
            msg = f"Duplicate prompt id: {prompt_id}"
            raise ValueError(msg)
        seen_ids.add(prompt_id)
        dimension_weights = {
            str(key): float(value)
            for key, value in dict(raw.get("dimension_weights", {})).items()
        }
        _validate_dimension_weights(prompt_id, dimension_weights, rubric)
        lookup_raw = dict(raw["lookup_probe"])
        prompts.append(
            EvalPrompt(
                prompt_id=prompt_id,
                family=str(raw["family"]),
                title=str(raw["title"]),
                suggested_pipeline=str(raw["suggested_pipeline"]),
                artifact_prompt=str(raw["artifact_prompt"]).strip(),
                output_expectation=str(raw["output_expectation"]).strip(),
                expected_quality_boosts=tuple(
                    str(item) for item in raw.get("expected_quality_boosts", [])
                ),
                dimension_weights=dimension_weights,
                lookup_probe=LookupProbeSpec(
                    tool=str(lookup_raw["tool"]),
                    query=str(lookup_raw["query"]),
                    top_k=int(lookup_raw.get("top_k", 5)),
                    required_patterns=tuple(
                        str(item) for item in lookup_raw.get("required_patterns", [])
                    ),
                    preferred_top_patterns=tuple(
                        str(item)
                        for item in lookup_raw.get("preferred_top_patterns", [])
                    ),
                ),
                notes=str(raw.get("notes", "")),
            )
        )
    return prompts


def load_milestones(eval_root: Path = EVAL_ROOT) -> list[MilestoneSpec]:
    """Load the git milestones to compare."""
    payload = _read_yaml(eval_root / "milestones.yaml")
    raw_milestones = payload.get("milestones", [])
    milestones: list[MilestoneSpec] = []
    seen_ids: set[str] = set()
    for raw in raw_milestones:
        if not isinstance(raw, dict):
            msg = "Milestone entries must be mappings"
            raise ValueError(msg)
        milestone_id = str(raw["id"])
        if milestone_id in seen_ids:
            msg = f"Duplicate milestone id: {milestone_id}"
            raise ValueError(msg)
        seen_ids.add(milestone_id)
        milestones.append(
            MilestoneSpec(
                milestone_id=milestone_id,
                label=str(raw["label"]),
                git_ref=str(raw["git_ref"]),
                description=str(raw["description"]),
            )
        )
    if not milestones:
        msg = "Milestones file must define at least one milestone"
        raise ValueError(msg)
    return milestones


def load_poster_artifact_suite(eval_root: Path = EVAL_ROOT) -> list[PosterArtifactCase]:
    """Load the frozen poster/UI artifact-run suite."""
    payload = _read_yaml(eval_root / "poster_ui_suite.yaml")
    raw_cases = payload.get("prompts", [])
    if not isinstance(raw_cases, list) or not raw_cases:
        msg = "Poster artifact suite must contain prompts"
        raise ValueError(msg)
    cases: list[PosterArtifactCase] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            msg = "Poster artifact cases must be mappings"
            raise ValueError(msg)
        prompt_id = str(raw["id"])
        if prompt_id in seen_ids:
            msg = f"Duplicate poster prompt id: {prompt_id}"
            raise ValueError(msg)
        seen_ids.add(prompt_id)
        cases.append(
            PosterArtifactCase(
                prompt_id=prompt_id,
                family=str(raw.get("family", "visual")),
                title=str(raw["title"]),
                prompt=str(raw["prompt"]).strip(),
                poster_inputs=dict(raw["poster_inputs"]),
                mock_brief_response=dict(raw["mock_brief_response"])
                if raw.get("mock_brief_response") is not None
                else None,
                expected_reference_tools=tuple(
                    str(item) for item in raw.get("expected_reference_tools", [])
                ),
                preferred_templates=tuple(
                    str(item) for item in raw.get("preferred_templates", [])
                ),
                discouraged_templates=tuple(
                    str(item) for item in raw.get("discouraged_templates", [])
                ),
                required_prompt_terms=tuple(
                    str(item) for item in raw.get("required_prompt_terms", [])
                ),
                manual_focus=tuple(str(item) for item in raw.get("manual_focus", [])),
            )
        )
    return cases


def resolve_git_ref(repo_root: Path, git_ref: str) -> str:
    """Resolve a git ref to a full commit SHA."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", git_ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_path_exists(repo_root: Path, git_ref: str, repo_path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{git_ref}:{repo_path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _git_read_text(repo_root: Path, git_ref: str, repo_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{git_ref}:{repo_path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def build_capability_snapshot(repo_root: Path, git_ref: str) -> dict[str, Any]:
    """Summarize which reference-eval capabilities exist at a git ref."""
    resolved_ref = resolve_git_ref(repo_root, git_ref)
    corpora_paths = [
        "references/ui_ux_pro_max/manifest.yaml",
        "references/vega_lite/manifest.yaml",
        "references/quarto/manifest.yaml",
    ]
    checks = {
        "reference_inventory": _git_path_exists(
            repo_root, git_ref, "references/inventory.py"
        ),
        "pinned_reference_corpora": all(
            _git_path_exists(repo_root, git_ref, path) for path in corpora_paths
        ),
        "lookup_layer_modules": all(
            _git_path_exists(repo_root, git_ref, path)
            for path in ("references/query.py", "references/search_engine.py")
        ),
        "ambient_reference_layer": _git_path_exists(
            repo_root, git_ref, "references/ambient.py"
        ),
        "eval_harness": _git_path_exists(
            repo_root, git_ref, "references/eval_harness.py"
        ),
    }
    if _git_path_exists(repo_root, git_ref, "plugins/design_intelligence/__init__.py"):
        plugin_text = _git_read_text(
            repo_root, git_ref, "plugins/design_intelligence/__init__.py"
        )
        checks["lookup_tool_registration"] = all(
            token in plugin_text
            for token in (
                "search_ui_styles",
                "search_ux_guidelines",
                "search_chart_patterns",
                "search_report_layouts",
                "search_quarto_layouts",
            )
        )
    else:
        checks["lookup_tool_registration"] = False
    checks["lookup_ready"] = bool(
        checks["lookup_layer_modules"] and checks["lookup_tool_registration"]
    )
    return {
        "git_ref": git_ref,
        "resolved_ref": resolved_ref,
        "checks": checks,
    }


@contextmanager
def _temporary_worktree(repo_root: Path, git_ref: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="vizier-reference-eval-") as tmpdir:
        worktree = Path(tmpdir)
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", "--detach", tmpdir, git_ref],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            yield worktree
        finally:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", "--force", tmpdir],
                check=True,
                capture_output=True,
                text=True,
            )


def _run_inline_python(
    *,
    source_root: Path,
    code: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(source_root)
        if not pythonpath
        else f"{source_root}{os.pathsep}{pythonpath}"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(source_root),
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "inline runner failed"
        raise RuntimeError(msg)
    return json.loads(result.stdout)


def _run_lookup_cases(source_root: Path, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = _run_inline_python(
        source_root=source_root,
        code=_LOOKUP_RUNNER_CODE,
        payload={"cases": cases},
    )
    return list(payload["results"])


def evaluate_lookup_probe(
    probe: LookupProbeSpec,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score one lookup probe result set against frozen expectations."""
    haystack = json.dumps(results, sort_keys=True, default=str).lower()
    top_haystack = (
        json.dumps(results[0], sort_keys=True, default=str).lower() if results else ""
    )
    matched_required = [
        pattern for pattern in probe.required_patterns if pattern.lower() in haystack
    ]
    matched_top = [
        pattern
        for pattern in probe.preferred_top_patterns
        if pattern.lower() in top_haystack
    ]
    required_denominator = max(len(probe.required_patterns), 1)
    top_denominator = max(len(probe.preferred_top_patterns), 1)
    required_score = len(matched_required) / required_denominator
    top_score = (
        len(matched_top) / top_denominator
        if probe.preferred_top_patterns
        else 1.0
    )
    score = round(((required_score * 0.75) + (top_score * 0.25)) * 100, 1)
    passed = (
        len(matched_required) == len(probe.required_patterns)
        and len(matched_top) == len(probe.preferred_top_patterns)
    )
    top_result = results[0] if results else {}
    top_summary = {
        key: top_result.get(key)
        for key in (
            "id",
            "name",
            "issue",
            "best_chart_type",
            "option",
            "pattern",
            "project_type",
            "renderer_tier",
            "dataset_id",
            "reference_family",
        )
        if key in top_result
    }
    return {
        "passed": passed,
        "score": score,
        "matched_required": matched_required,
        "missing_required": [
            pattern
            for pattern in probe.required_patterns
            if pattern not in matched_required
        ],
        "matched_top": matched_top,
        "missing_top": [
            pattern
            for pattern in probe.preferred_top_patterns
            if pattern not in matched_top
        ],
        "top_result": top_summary,
        "result_count": len(results),
    }


def summarize_lookup_probe_suite(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate lookup probe results by family."""
    completed = [result for result in results if result["status"] == "completed"]
    by_family: dict[str, list[dict[str, Any]]] = {}
    for result in completed:
        by_family.setdefault(str(result["family"]), []).append(result)
    family_scores = {
        family: round(
            sum(float(item["score"]) for item in family_results) / len(family_results), 1
        )
        for family, family_results in by_family.items()
    }
    pass_count = sum(1 for result in completed if result["passed"])
    overall_score = (
        round(sum(float(result["score"]) for result in completed) / len(completed), 1)
        if completed
        else 0.0
    )
    return {
        "case_count": len(results),
        "completed_case_count": len(completed),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(completed), 3) if completed else 0.0,
        "average_score": overall_score,
        "family_scores": family_scores,
    }


def run_lookup_probe_suite(
    repo_root: Path,
    git_ref: str,
    prompts: list[EvalPrompt] | None = None,
    capability_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run frozen lookup probes against one git ref."""
    prompts = prompts or load_prompt_suite()
    snapshot = capability_snapshot or build_capability_snapshot(repo_root, git_ref)
    if not snapshot["checks"]["lookup_ready"]:
        unavailable_results = [
            {
                "prompt_id": prompt.prompt_id,
                "family": prompt.family,
                "tool": prompt.lookup_probe.tool,
                "status": "unavailable",
                "passed": False,
                "score": 0.0,
                "matched_required": [],
                "missing_required": list(prompt.lookup_probe.required_patterns),
                "matched_top": [],
                "missing_top": list(prompt.lookup_probe.preferred_top_patterns),
                "top_result": {},
                "result_count": 0,
                "error": "lookup layer unavailable at this milestone",
            }
            for prompt in prompts
        ]
        return {
            "git_ref": git_ref,
            "resolved_ref": snapshot["resolved_ref"],
            "status": "unavailable",
            "results": unavailable_results,
            "summary": summarize_lookup_probe_suite(unavailable_results),
        }

    cases = [
        {
            "prompt_id": prompt.prompt_id,
            "tool": prompt.lookup_probe.tool,
            "query": prompt.lookup_probe.query,
            "top_k": prompt.lookup_probe.top_k,
        }
        for prompt in prompts
    ]

    with _temporary_worktree(repo_root, git_ref) as source_root:
        lookup_results = _run_lookup_cases(source_root, cases)

    by_prompt_id = {item["prompt_id"]: item for item in lookup_results}
    evaluated_results: list[dict[str, Any]] = []
    for prompt in prompts:
        raw = by_prompt_id[prompt.prompt_id]
        probe_summary = evaluate_lookup_probe(prompt.lookup_probe, list(raw["results"]))
        evaluated_results.append(
            {
                "prompt_id": prompt.prompt_id,
                "family": prompt.family,
                "tool": prompt.lookup_probe.tool,
                "query": prompt.lookup_probe.query,
                "status": "completed",
                **probe_summary,
            }
        )
    return {
        "git_ref": git_ref,
        "resolved_ref": snapshot["resolved_ref"],
        "status": "completed",
        "results": evaluated_results,
        "summary": summarize_lookup_probe_suite(evaluated_results),
    }


def build_blank_scorecard(
    *,
    milestone_id: str,
    git_ref: str,
    resolved_ref: str,
    evaluator: str = "human",
    system_under_test: str = "reference-aware artifact generation",
    prompts: list[EvalPrompt] | None = None,
) -> dict[str, Any]:
    """Create a blank manual scorecard for the frozen prompt suite."""
    prompts = prompts or load_prompt_suite()
    return {
        "schema_version": 1,
        "suite_id": "reference_corpus_quality_v2",
        "generated_at": _utc_now(),
        "evaluator": evaluator,
        "system_under_test": system_under_test,
        "milestone": {
            "id": milestone_id,
            "git_ref": git_ref,
            "resolved_ref": resolved_ref,
        },
        "results": [
            {
                "prompt_id": prompt.prompt_id,
                "family": prompt.family,
                "title": prompt.title,
                "suggested_pipeline": prompt.suggested_pipeline,
                "artifact_path": "",
                "consulted_tools": [],
                "notes": "",
                "dimension_scores": {
                    dimension_id: None for dimension_id in prompt.dimension_weights
                },
            }
            for prompt in prompts
        ],
    }


def validate_scorecard(
    scorecard: dict[str, Any],
    prompts: list[EvalPrompt] | None = None,
    *,
    allow_unscored: bool = False,
) -> None:
    """Validate scorecard shape and score ranges."""
    prompts = prompts or load_prompt_suite()
    prompt_map = {prompt.prompt_id: prompt for prompt in prompts}
    results = scorecard.get("results")
    if not isinstance(results, list):
        msg = "Scorecard results must be a list"
        raise ValueError(msg)
    seen_prompt_ids: set[str] = set()
    for entry in results:
        if not isinstance(entry, dict):
            msg = "Scorecard entries must be mappings"
            raise ValueError(msg)
        prompt_id = str(entry["prompt_id"])
        if prompt_id not in prompt_map:
            msg = f"Unknown prompt_id in scorecard: {prompt_id}"
            raise ValueError(msg)
        if prompt_id in seen_prompt_ids:
            msg = f"Duplicate prompt_id in scorecard: {prompt_id}"
            raise ValueError(msg)
        seen_prompt_ids.add(prompt_id)
        expected_dimensions = set(prompt_map[prompt_id].dimension_weights)
        dimension_scores = dict(entry.get("dimension_scores", {}))
        if set(dimension_scores) != expected_dimensions:
            msg = (
                f"Scorecard dimensions for {prompt_id} must match suite weights: "
                f"{sorted(expected_dimensions)}"
            )
            raise ValueError(msg)
        for dimension_id, score in dimension_scores.items():
            if score is None:
                if allow_unscored:
                    continue
                msg = f"Scorecard score for {prompt_id}/{dimension_id} is missing"
                raise ValueError(msg)
            if not isinstance(score, int):
                msg = f"Scorecard score for {prompt_id}/{dimension_id} must be an int"
                raise ValueError(msg)
            if score < SCORE_MIN or score > SCORE_MAX:
                msg = (
                    f"Scorecard score for {prompt_id}/{dimension_id} must be between "
                    f"{SCORE_MIN} and {SCORE_MAX}"
                )
                raise ValueError(msg)
    expected_prompt_ids = set(prompt_map)
    if seen_prompt_ids != expected_prompt_ids:
        missing = sorted(expected_prompt_ids - seen_prompt_ids)
        msg = f"Scorecard is missing prompts: {missing}"
        raise ValueError(msg)


def summarize_scorecard(
    scorecard: dict[str, Any],
    prompts: list[EvalPrompt] | None = None,
) -> dict[str, Any]:
    """Aggregate a completed manual scorecard."""
    prompts = prompts or load_prompt_suite()
    validate_scorecard(scorecard, prompts, allow_unscored=False)
    prompt_map = {prompt.prompt_id: prompt for prompt in prompts}
    per_prompt: list[dict[str, Any]] = []
    by_family: dict[str, list[float]] = {}
    by_dimension: dict[str, list[int]] = {}

    for entry in scorecard["results"]:
        prompt = prompt_map[str(entry["prompt_id"])]
        dimension_scores = dict(entry["dimension_scores"])
        weighted_score = sum(
            int(dimension_scores[dimension_id]) * weight
            for dimension_id, weight in prompt.dimension_weights.items()
        )
        per_prompt.append(
            {
                "prompt_id": prompt.prompt_id,
                "family": prompt.family,
                "score_5": round(weighted_score, 3),
                "score_10": round(weighted_score * 2.0, 3),
            }
        )
        by_family.setdefault(prompt.family, []).append(weighted_score)
        for dimension_id, score in dimension_scores.items():
            by_dimension.setdefault(dimension_id, []).append(int(score))

    overall_score_5 = round(
        sum(item["score_5"] for item in per_prompt) / len(per_prompt), 3
    )
    return {
        "overall_score_5": overall_score_5,
        "overall_score_10": round(overall_score_5 * 2.0, 3),
        "prompt_count": len(per_prompt),
        "family_scores_5": {
            family: round(sum(scores) / len(scores), 3)
            for family, scores in by_family.items()
        },
        "dimension_scores": {
            dimension_id: round(sum(scores) / len(scores), 3)
            for dimension_id, scores in by_dimension.items()
        },
        "per_prompt": per_prompt,
    }


def compare_scorecards(
    scorecards: list[dict[str, Any]],
    prompts: list[EvalPrompt] | None = None,
) -> dict[str, Any]:
    """Compare multiple completed scorecards."""
    prompts = prompts or load_prompt_suite()
    comparison = []
    for scorecard in scorecards:
        summary = summarize_scorecard(scorecard, prompts)
        milestone = dict(scorecard.get("milestone", {}))
        comparison.append(
            {
                "milestone_id": milestone.get("id"),
                "git_ref": milestone.get("git_ref"),
                "resolved_ref": milestone.get("resolved_ref"),
                "overall_score_5": summary["overall_score_5"],
                "overall_score_10": summary["overall_score_10"],
                "family_scores_5": summary["family_scores_5"],
            }
        )
    deltas: list[dict[str, Any]] = []
    for previous, current in zip(comparison, comparison[1:]):
        deltas.append(
            {
                "from": previous["milestone_id"],
                "to": current["milestone_id"],
                "overall_delta_5": round(
                    float(current["overall_score_5"]) - float(previous["overall_score_5"]),
                    3,
                ),
            }
        )
    return {
        "milestones": comparison,
        "deltas": deltas,
    }


def probe_milestones(
    repo_root: Path = REPO_ROOT,
    milestones: list[MilestoneSpec] | None = None,
    prompts: list[EvalPrompt] | None = None,
) -> dict[str, Any]:
    """Run the deterministic capability and lookup comparison across milestones."""
    milestones = milestones or load_milestones()
    prompts = prompts or load_prompt_suite()
    rows = []
    for milestone in milestones:
        capability = build_capability_snapshot(repo_root, milestone.git_ref)
        lookup = run_lookup_probe_suite(
            repo_root,
            milestone.git_ref,
            prompts=prompts,
            capability_snapshot=capability,
        )
        rows.append(
            {
                "milestone_id": milestone.milestone_id,
                "label": milestone.label,
                "description": milestone.description,
                "git_ref": milestone.git_ref,
                "resolved_ref": capability["resolved_ref"],
                "capability": capability["checks"],
                "lookup_probe": {
                    "status": lookup["status"],
                    "summary": lookup["summary"],
                    "results": lookup["results"],
                },
            }
        )
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "suite_id": "reference_corpus_quality_v2",
        "milestones": rows,
    }


def render_probe_report_markdown(report: dict[str, Any]) -> str:
    """Render a concise markdown summary of milestone probe results."""
    lines = [
        "# Reference Corpus Eval Probe",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        "## Capability Matrix",
        "",
        "| Milestone | Ref | Corpora | Lookup | Ambient | Eval Harness | Probe Status | Avg Probe Score |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for row in report["milestones"]:
        capability = row["capability"]
        summary = row["lookup_probe"]["summary"]
        lines.append(
            "| "
            f"{row['label']} | `{row['resolved_ref'][:8]}` | "
            f"{'yes' if capability['pinned_reference_corpora'] else 'no'} | "
            f"{'yes' if capability['lookup_ready'] else 'no'} | "
            f"{'yes' if capability['ambient_reference_layer'] else 'no'} | "
            f"{'yes' if capability['eval_harness'] else 'no'} | "
            f"{row['lookup_probe']['status']} | "
            f"{summary['average_score']:.1f} |"
        )

    lines.extend(["", "## Lookup Probe Notes", ""])
    for row in report["milestones"]:
        summary = row["lookup_probe"]["summary"]
        lines.append(
            f"- {row['label']}: "
            f"{summary['pass_count']}/{summary['completed_case_count']} completed cases passed; "
            f"family averages = {summary['family_scores']}"
        )
    return "\n".join(lines) + "\n"


def _contains_generic_cta(cta: str) -> bool:
    return cta.strip().lower() in {"", "learn more", "discover more", "find out more"}


def _score_reference_usage(
    case: PosterArtifactCase,
    result: dict[str, Any],
) -> dict[str, Any]:
    trace = dict(result.get("reference_trace") or {})
    tools = {str(item) for item in trace.get("lookup_tools_used", [])}
    expected = set(case.expected_reference_tools)
    coverage = len(expected & tools) / max(len(expected), 1)
    influences = list(trace.get("material_influences") or [])
    influence_bonus = 0.0
    if len(influences) >= 3:
        influence_bonus = 0.25
    elif len(influences) >= 1:
        influence_bonus = 0.1
    score = round(min(1.0, (coverage * 0.75) + influence_bonus) * 100, 1)
    return {
        "score": score,
        "expected_tools": sorted(expected),
        "used_tools": sorted(tools),
        "material_influence_count": len(influences),
        "passed": coverage == 1.0 and len(influences) >= 2,
    }


def _score_copy_discipline(result: dict[str, Any]) -> dict[str, Any]:
    brief = dict(result.get("creative_brief") or {})
    headline = str(brief.get("headline", ""))
    body = str(brief.get("body", ""))
    cta = str(brief.get("cta", ""))
    headline_words = len([word for word in headline.split() if word])
    body_chars = len(body.strip())
    cta_words = len([word for word in cta.split() if word])
    headline_ok = 2 <= headline_words <= 8
    body_ok = 1 <= body_chars <= 140
    cta_ok = 1 <= cta_words <= 3 and not _contains_generic_cta(cta)
    score = 0.0
    score += 35.0 if headline_ok else 10.0
    score += 30.0 if body_ok else 10.0
    score += 35.0 if cta_ok else 10.0
    return {
        "score": round(score, 1),
        "headline_words": headline_words,
        "body_chars": body_chars,
        "cta_words": cta_words,
        "headline": headline,
        "body": body,
        "cta": cta,
        "passed": headline_ok and body_ok and cta_ok,
    }


def _score_template_fit(
    case: PosterArtifactCase,
    result: dict[str, Any],
) -> dict[str, Any]:
    template_used = str(result.get("template_used", ""))
    if case.preferred_templates and template_used in case.preferred_templates:
        score = 100.0
    elif case.discouraged_templates and template_used in case.discouraged_templates:
        score = 20.0
    elif case.preferred_templates:
        score = 55.0
    else:
        score = 70.0
    return {
        "score": score,
        "template_used": template_used,
        "preferred_templates": list(case.preferred_templates),
        "discouraged_templates": list(case.discouraged_templates),
        "passed": score >= 80.0,
    }


def _score_prompt_guardrails(
    case: PosterArtifactCase,
    result: dict[str, Any],
) -> dict[str, Any]:
    prompt_trace = dict(result.get("prompt_trace") or {})
    prompt = str(prompt_trace.get("effective_prompt", "")).lower()
    if not prompt:
        return {
            "score": 0.0,
            "matched_terms": [],
            "missing_terms": list(case.required_prompt_terms),
            "passed": False,
        }
    matched = [
        term for term in case.required_prompt_terms if term.lower() in prompt
    ]
    denominator = max(len(case.required_prompt_terms), 1)
    score = round((len(matched) / denominator) * 100, 1)
    return {
        "score": score,
        "matched_terms": matched,
        "missing_terms": [
            term for term in case.required_prompt_terms if term not in matched
        ],
        "passed": len(matched) == len(case.required_prompt_terms),
    }


def _score_trace_persistence(result: dict[str, Any]) -> dict[str, Any]:
    trace_path = str(result.get("trace_path", ""))
    exists = bool(trace_path) and Path(trace_path).exists()
    score = 100.0 if exists else 0.0
    return {
        "score": score,
        "trace_path": trace_path,
        "passed": exists,
    }


def score_poster_artifact_result(
    case: PosterArtifactCase,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Score one poster artifact run using deterministic quality proxies."""
    checks = {
        "reference_usage": _score_reference_usage(case, result),
        "copy_discipline": _score_copy_discipline(result),
        "template_fit": _score_template_fit(case, result),
        "prompt_guardrails": _score_prompt_guardrails(case, result),
        "trace_persistence": _score_trace_persistence(result),
    }
    weighted_score = (
        checks["reference_usage"]["score"] * 0.30
        + checks["copy_discipline"]["score"] * 0.20
        + checks["template_fit"]["score"] * 0.20
        + checks["prompt_guardrails"]["score"] * 0.20
        + checks["trace_persistence"]["score"] * 0.10
    )
    return {
        "objective_checks": checks,
        "objective_score_100": round(weighted_score, 1),
        "manual_review": {
            "status": "required",
            "dimensions": {dimension: None for dimension in POSTER_MANUAL_DIMENSIONS},
            "focus": list(case.manual_focus),
        },
    }


def summarize_poster_suite_run(report: dict[str, Any]) -> dict[str, Any]:
    """Aggregate one poster-suite report."""
    cases = list(report.get("cases", []))
    if not cases:
        return {
            "case_count": 0,
            "average_objective_score_100": 0.0,
            "check_averages": {},
        }
    check_averages: dict[str, float] = {}
    for check_name in (
        "reference_usage",
        "copy_discipline",
        "template_fit",
        "prompt_guardrails",
        "trace_persistence",
    ):
        check_averages[check_name] = round(
            sum(
                float(case["objective_checks"][check_name]["score"])
                for case in cases
            )
            / len(cases),
            1,
        )
    return {
        "case_count": len(cases),
        "average_objective_score_100": round(
            sum(float(case["objective_score_100"]) for case in cases) / len(cases),
            1,
        ),
        "check_averages": check_averages,
    }


def run_poster_artifact_suite(
    *,
    repo_root: Path = REPO_ROOT,
    git_ref: str = "HEAD",
    cases: list[PosterArtifactCase] | None = None,
    output_root: Path | None = None,
    label: str = "",
) -> dict[str, Any]:
    """Run the poster/UI artifact suite against a specific git ref."""
    cases = cases or load_poster_artifact_suite()
    if git_ref == "WORKTREE":
        resolved_ref = f"{resolve_git_ref(repo_root, 'HEAD')}+working-tree"
    else:
        resolved_ref = resolve_git_ref(repo_root, git_ref)
    output_root = output_root or (
        EVAL_ROOT / "results" / f"{resolved_ref[:8]}-poster-artifacts"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    runner_payload = {
        "output_root": str(output_root),
        "cases": [
            {
                "prompt_id": case.prompt_id,
                "poster_inputs": case.poster_inputs,
                "mock_brief_response": case.mock_brief_response,
            }
            for case in cases
        ],
    }
    if git_ref == "WORKTREE":
        raw_results = _run_inline_python(
            source_root=repo_root,
            code=_POSTER_RUNNER_CODE,
            payload=runner_payload,
        )
    else:
        with _temporary_worktree(repo_root, git_ref) as source_root:
            raw_results = _run_inline_python(
                source_root=source_root,
                code=_POSTER_RUNNER_CODE,
                payload=runner_payload,
            )

    by_prompt_id = {
        str(item["prompt_id"]): dict(item["result"])
        for item in raw_results["results"]
    }
    rendered_cases: list[dict[str, Any]] = []
    for case in cases:
        result = by_prompt_id[case.prompt_id]
        scored = score_poster_artifact_result(case, result)
        rendered_cases.append(
            {
                "prompt_id": case.prompt_id,
                "family": case.family,
                "title": case.title,
                "prompt": case.prompt,
                "artifact_path": result.get("poster_path", ""),
                "trace_path": result.get("trace_path", ""),
                "template_used": result.get("template_used", ""),
                "creative_brief": result.get("creative_brief", {}),
                "reference_trace": result.get("reference_trace", {}),
                "art_direction_plan": result.get("art_direction_plan", {}),
                "template_reason": result.get("template_reason", ""),
                "prompt_trace": result.get("prompt_trace", {}),
                **scored,
            }
        )
    report = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "kind": "poster_ui_artifact_eval",
        "label": label or git_ref,
        "git_ref": git_ref,
        "resolved_ref": resolved_ref,
        "output_root": str(output_root),
        "cases": rendered_cases,
    }
    report["summary"] = summarize_poster_suite_run(report)
    return report


def compare_poster_suite_runs(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare before/after poster artifact reports."""
    run_summaries = []
    for report in reports:
        summary = report.get("summary") or summarize_poster_suite_run(report)
        run_summaries.append(
            {
                "label": report.get("label"),
                "git_ref": report.get("git_ref"),
                "resolved_ref": report.get("resolved_ref"),
                "average_objective_score_100": summary["average_objective_score_100"],
                "check_averages": summary["check_averages"],
            }
        )
    deltas: list[dict[str, Any]] = []
    case_deltas: list[dict[str, Any]] = []
    for previous, current in zip(reports, reports[1:]):
        prev_summary = previous.get("summary") or summarize_poster_suite_run(previous)
        curr_summary = current.get("summary") or summarize_poster_suite_run(current)
        deltas.append(
            {
                "from": previous.get("label"),
                "to": current.get("label"),
                "objective_delta_100": round(
                    float(curr_summary["average_objective_score_100"])
                    - float(prev_summary["average_objective_score_100"]),
                    1,
                ),
                "check_deltas": {
                    check_name: round(
                        float(curr_summary["check_averages"].get(check_name, 0.0))
                        - float(prev_summary["check_averages"].get(check_name, 0.0)),
                        1,
                    )
                    for check_name in curr_summary["check_averages"]
                },
            }
        )
        prev_cases = {case["prompt_id"]: case for case in previous.get("cases", [])}
        curr_cases = {case["prompt_id"]: case for case in current.get("cases", [])}
        for prompt_id, curr_case in curr_cases.items():
            prev_case = prev_cases.get(prompt_id)
            if prev_case is None:
                continue
            case_deltas.append(
                {
                    "prompt_id": prompt_id,
                    "from_label": previous.get("label"),
                    "to_label": current.get("label"),
                    "objective_delta_100": round(
                        float(curr_case["objective_score_100"])
                        - float(prev_case["objective_score_100"]),
                        1,
                    ),
                    "template_before": prev_case.get("template_used"),
                    "template_after": curr_case.get("template_used"),
                }
            )
    return {
        "runs": run_summaries,
        "deltas": deltas,
        "case_deltas": case_deltas,
    }


def render_poster_suite_markdown(report: dict[str, Any]) -> str:
    """Render a concise markdown summary for one poster artifact report."""
    lines = [
        "# Poster/UI Artifact Eval",
        "",
        f"Label: {report['label']}",
        f"Git ref: `{report['git_ref']}` (`{report['resolved_ref'][:8]}`)",
        f"Generated at: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Average objective score: {report['summary']['average_objective_score_100']:.1f}/100",
        f"- Check averages: {report['summary']['check_averages']}",
        "",
        "## Cases",
        "",
        "| Prompt | Template | Objective | Reference Tools |",
        "| --- | --- | ---: | --- |",
    ]
    for case in report["cases"]:
        tools = ", ".join(case["reference_trace"].get("lookup_tools_used", []))
        lines.append(
            f"| {case['prompt_id']} | {case['template_used']} | "
            f"{case['objective_score_100']:.1f} | {tools or 'none'} |"
        )
    lines.extend(["", "## Notes", ""])
    for case in report["cases"]:
        lines.append(
            f"- {case['prompt_id']}: "
            f"{case['objective_checks']['copy_discipline']['cta']} CTA, "
            f"template `{case['template_used']}`, "
            f"manual focus = {case['manual_review']['focus']}"
        )
    return "\n".join(lines) + "\n"
