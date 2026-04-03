"""Tests for the reference-corpus evaluation harness."""
from __future__ import annotations

from pathlib import Path

import pytest

from references.eval_harness import (
    POSTER_MANUAL_DIMENSIONS,
    REPO_ROOT,
    LookupProbeSpec,
    build_blank_scorecard,
    build_capability_snapshot,
    compare_poster_suite_runs,
    compare_scorecards,
    evaluate_lookup_probe,
    load_milestones,
    load_poster_artifact_suite,
    load_prompt_suite,
    load_rubric,
    score_poster_artifact_result,
    summarize_scorecard,
    validate_scorecard,
)


def _filled_scorecard(score: int) -> dict[str, object]:
    prompts = load_prompt_suite()
    scorecard = build_blank_scorecard(
        milestone_id=f"score-{score}",
        git_ref="HEAD",
        resolved_ref="deadbeef" * 5,
        prompts=prompts,
    )
    for entry in scorecard["results"]:
        dimension_scores = dict(entry["dimension_scores"])
        for dimension_id in dimension_scores:
            dimension_scores[dimension_id] = score
        entry["dimension_scores"] = dimension_scores
    return scorecard


def test_prompt_suite_covers_visual_chart_and_report() -> None:
    prompts = load_prompt_suite()

    assert len(prompts) >= 6
    families = {prompt.family for prompt in prompts}
    assert families == {"visual", "chart", "report"}


def test_prompt_dimension_weights_sum_to_one() -> None:
    prompts = load_prompt_suite()
    rubric = load_rubric()

    for prompt in prompts:
        assert set(prompt.dimension_weights) <= set(rubric)
        assert abs(sum(prompt.dimension_weights.values()) - 1.0) < 0.001


def test_poster_artifact_suite_focuses_on_visual_cases() -> None:
    cases = load_poster_artifact_suite()

    assert len(cases) == 4
    assert {case.family for case in cases} == {"visual"}
    assert all(case.expected_reference_tools for case in cases)


def test_milestones_include_expected_reference_points() -> None:
    milestones = load_milestones()
    milestone_ids = [milestone.milestone_id for milestone in milestones]

    assert milestone_ids == [
        "baseline_pre_reference_corpora",
        "import_foundation",
        "lookup_layer",
        "ambient_reference_capability",
        "current_head",
    ]


def test_blank_scorecard_validates_when_unscored_allowed() -> None:
    scorecard = build_blank_scorecard(
        milestone_id="current_head",
        git_ref="HEAD",
        resolved_ref="deadbeef" * 5,
    )

    validate_scorecard(scorecard, allow_unscored=True)


def test_validate_scorecard_rejects_missing_scores_when_completed() -> None:
    scorecard = build_blank_scorecard(
        milestone_id="current_head",
        git_ref="HEAD",
        resolved_ref="deadbeef" * 5,
    )

    with pytest.raises(ValueError, match="is missing"):
        validate_scorecard(scorecard, allow_unscored=False)


def test_summarize_scorecard_with_uniform_scores() -> None:
    scorecard = _filled_scorecard(4)

    summary = summarize_scorecard(scorecard)

    assert summary["overall_score_5"] == 4.0
    assert summary["overall_score_10"] == 8.0
    assert summary["prompt_count"] == len(load_prompt_suite())
    assert summary["family_scores_5"]["visual"] == 4.0


def test_compare_scorecards_reports_expected_delta() -> None:
    low = _filled_scorecard(3)
    high = _filled_scorecard(4)
    high["milestone"]["id"] = "score-4"

    comparison = compare_scorecards([low, high])

    assert comparison["milestones"][0]["overall_score_5"] == 3.0
    assert comparison["milestones"][1]["overall_score_5"] == 4.0
    assert comparison["deltas"] == [
        {"from": "score-3", "to": "score-4", "overall_delta_5": 1.0}
    ]


def test_evaluate_lookup_probe_matches_expected_patterns() -> None:
    probe = LookupProbeSpec(
        tool="search_ui_styles",
        query="enterprise dashboard swiss grid",
        top_k=5,
        required_patterns=("ui_styles", "swiss", "dashboard"),
        preferred_top_patterns=("minimalism & swiss style",),
    )
    results = [
        {
            "dataset_id": "ui_styles",
            "reference_family": "ui_ux_pro_max",
            "name": "Minimalism & Swiss Style",
            "best_for": ["Enterprise dashboards"],
        }
    ]

    summary = evaluate_lookup_probe(probe, results)

    assert summary["passed"] is True
    assert summary["score"] == 100.0
    assert summary["missing_required"] == []
    assert summary["missing_top"] == []


def test_build_capability_snapshot_current_head_has_corpora_lookup_and_eval() -> None:
    snapshot = build_capability_snapshot(REPO_ROOT, "HEAD")

    assert snapshot["checks"]["reference_inventory"] is True
    assert snapshot["checks"]["pinned_reference_corpora"] is True
    assert snapshot["checks"]["lookup_layer_modules"] is True
    assert snapshot["checks"]["lookup_tool_registration"] is True
    assert snapshot["checks"]["lookup_ready"] is True
    assert (REPO_ROOT / "references" / "eval_harness.py").exists()


def test_score_poster_artifact_result_rewards_trace_copy_and_template_fit(
    tmp_path: Path,
) -> None:
    case = load_poster_artifact_suite()[0]
    trace_path = tmp_path / "poster.trace.json"
    trace_path.write_text("{}", encoding="utf-8")

    scored = score_poster_artifact_result(
        case,
        {
            "creative_brief": {
                "headline": "Finance Without Noise",
                "body": "Help CFOs scan runway and risk faster.",
                "cta": "Book Demo",
            },
            "reference_trace": {
                "lookup_tools_used": ["search_ui_styles", "search_ux_guidelines"],
                "material_influences": [{}, {}, {}],
            },
            "template_used": "editorial-split-square",
            "prompt_trace": {
                "effective_prompt": "grid contrast negative space cta premium hero",
            },
            "trace_path": str(trace_path),
        },
    )

    assert scored["objective_score_100"] >= 90.0
    assert set(scored["manual_review"]["dimensions"]) == set(POSTER_MANUAL_DIMENSIONS)


def test_compare_poster_suite_runs_reports_case_and_overall_deltas() -> None:
    before = {
        "label": "before",
        "git_ref": "abc",
        "resolved_ref": "a" * 40,
        "summary": {
            "average_objective_score_100": 50.0,
            "check_averages": {
                "reference_usage": 20.0,
                "copy_discipline": 60.0,
                "template_fit": 30.0,
                "prompt_guardrails": 40.0,
                "trace_persistence": 0.0,
            },
        },
        "cases": [
            {
                "prompt_id": "swiss_analytics_hero",
                "objective_score_100": 45.0,
                "template_used": "social-post",
            }
        ],
    }
    after = {
        "label": "after",
        "git_ref": "def",
        "resolved_ref": "b" * 40,
        "summary": {
            "average_objective_score_100": 82.0,
            "check_averages": {
                "reference_usage": 90.0,
                "copy_discipline": 78.0,
                "template_fit": 85.0,
                "prompt_guardrails": 88.0,
                "trace_persistence": 100.0,
            },
        },
        "cases": [
            {
                "prompt_id": "swiss_analytics_hero",
                "objective_score_100": 83.0,
                "template_used": "editorial-split-square",
            }
        ],
    }

    comparison = compare_poster_suite_runs([before, after])

    assert comparison["deltas"][0]["objective_delta_100"] == 32.0
    assert comparison["case_deltas"][0]["objective_delta_100"] == 38.0
    assert comparison["case_deltas"][0]["template_before"] == "social-post"
    assert comparison["case_deltas"][0]["template_after"] == "editorial-split-square"
