#!/usr/bin/env python3
"""CLI for the reference-corpus evaluation harness."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from references.eval_harness import (
    REPO_ROOT,
    build_blank_scorecard,
    build_blank_poster_manual_scorecard,
    compare_poster_suite_runs,
    compare_poster_manual_scorecards,
    compare_scorecards,
    load_milestones,
    probe_milestones,
    render_poster_suite_markdown,
    render_probe_report_markdown,
    resolve_git_ref,
    run_poster_artifact_suite,
    summarize_poster_manual_scorecard,
    summarize_scorecard,
    validate_poster_manual_scorecard,
    validate_scorecard,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(payload: dict[str, Any], path: Path | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    if path is None:
        print(text, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_text(text: str, path: Path | None) -> None:
    if path is None:
        print(text, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _milestone_ref_from_args(
    milestone_id: str | None,
    git_ref: str | None,
) -> tuple[str, str]:
    if milestone_id is None and git_ref is None:
        return ("current_head", "HEAD")
    if milestone_id is not None and git_ref is not None:
        return (milestone_id, git_ref)
    if milestone_id is not None:
        milestone_map = {item.milestone_id: item for item in load_milestones()}
        if milestone_id not in milestone_map:
            msg = f"Unknown milestone id: {milestone_id}"
            raise ValueError(msg)
        return (milestone_id, milestone_map[milestone_id].git_ref)
    return ("custom", str(git_ref))


def command_probe_milestones(args: argparse.Namespace) -> int:
    report = probe_milestones(repo_root=Path(args.repo_root))
    _write_json(report, Path(args.output_json) if args.output_json else None)
    if args.output_markdown:
        markdown = render_probe_report_markdown(report)
        _write_text(markdown, Path(args.output_markdown))
    return 0


def command_prepare_scorecard(args: argparse.Namespace) -> int:
    milestone_id, git_ref = _milestone_ref_from_args(args.milestone_id, args.git_ref)
    repo_root = Path(args.repo_root)
    scorecard = build_blank_scorecard(
        milestone_id=milestone_id,
        git_ref=git_ref,
        resolved_ref=resolve_git_ref(repo_root, git_ref),
        evaluator=args.evaluator,
        system_under_test=args.system_under_test,
    )
    _write_json(scorecard, Path(args.output))
    return 0


def command_validate_scorecard(args: argparse.Namespace) -> int:
    scorecard = _read_json(Path(args.path))
    validate_scorecard(scorecard, allow_unscored=args.allow_unscored)
    print(
        json.dumps(
            {
                "status": "ok",
                "path": args.path,
                "allow_unscored": bool(args.allow_unscored),
            },
            indent=2,
        )
    )
    return 0


def command_summarize_scorecard(args: argparse.Namespace) -> int:
    scorecard = _read_json(Path(args.path))
    summary = summarize_scorecard(scorecard)
    _write_json(summary, Path(args.output) if args.output else None)
    return 0


def command_compare_scorecards(args: argparse.Namespace) -> int:
    scorecards = [_read_json(Path(path)) for path in args.paths]
    comparison = compare_scorecards(scorecards)
    _write_json(comparison, Path(args.output) if args.output else None)
    return 0


def command_run_poster_suite(args: argparse.Namespace) -> int:
    label, git_ref = _milestone_ref_from_args(args.milestone_id, args.git_ref)
    output_root = Path(args.output_root) if args.output_root else None
    report = run_poster_artifact_suite(
        repo_root=Path(args.repo_root),
        git_ref=git_ref,
        output_root=output_root,
        label=args.label or label,
    )
    _write_json(report, Path(args.output_json) if args.output_json else None)
    if args.output_markdown:
        markdown = render_poster_suite_markdown(report)
        _write_text(markdown, Path(args.output_markdown))
    return 0


def command_compare_poster_runs(args: argparse.Namespace) -> int:
    reports = [_read_json(Path(path)) for path in args.paths]
    comparison = compare_poster_suite_runs(reports)
    _write_json(comparison, Path(args.output) if args.output else None)
    return 0


def command_prepare_poster_scorecard(args: argparse.Namespace) -> int:
    report = _read_json(Path(args.report))
    scorecard = build_blank_poster_manual_scorecard(
        report,
        evaluator=args.evaluator,
    )
    _write_json(scorecard, Path(args.output))
    return 0


def command_validate_poster_scorecard(args: argparse.Namespace) -> int:
    scorecard = _read_json(Path(args.path))
    report = _read_json(Path(args.report))
    validate_poster_manual_scorecard(
        scorecard,
        report,
        allow_unscored=args.allow_unscored,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "path": args.path,
                "report": args.report,
                "allow_unscored": bool(args.allow_unscored),
            },
            indent=2,
        )
    )
    return 0


def command_summarize_poster_scorecard(args: argparse.Namespace) -> int:
    scorecard = _read_json(Path(args.path))
    report = _read_json(Path(args.report))
    summary = summarize_poster_manual_scorecard(scorecard, report)
    _write_json(summary, Path(args.output) if args.output else None)
    return 0


def command_compare_poster_scorecards(args: argparse.Namespace) -> int:
    scorecards = [_read_json(Path(path)) for path in args.paths]
    reports = [_read_json(Path(path)) for path in args.reports]
    comparison = compare_poster_manual_scorecards(scorecards, reports)
    _write_json(comparison, Path(args.output) if args.output else None)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the reference-corpus evaluation harness."
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root to inspect. Defaults to the current repo root.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser(
        "probe-milestones",
        help="Run the deterministic capability and lookup probe across frozen milestones.",
    )
    probe_parser.add_argument("--output-json", help="Write the JSON report to this path.")
    probe_parser.add_argument(
        "--output-markdown",
        help="Write a human-readable markdown summary to this path.",
    )
    probe_parser.set_defaults(func=command_probe_milestones)

    prepare_parser = subparsers.add_parser(
        "prepare-scorecard",
        help="Generate a blank manual scorecard for one milestone.",
    )
    prepare_parser.add_argument("--milestone-id", help="Milestone id from milestones.yaml.")
    prepare_parser.add_argument("--git-ref", help="Explicit git ref to resolve.")
    prepare_parser.add_argument("--output", required=True, help="Where to write the JSON template.")
    prepare_parser.add_argument(
        "--evaluator",
        default="human",
        help="Who will score the artifacts. Defaults to 'human'.",
    )
    prepare_parser.add_argument(
        "--system-under-test",
        default="reference-aware artifact generation",
        help="Short label for the system being evaluated.",
    )
    prepare_parser.set_defaults(func=command_prepare_scorecard)

    validate_parser = subparsers.add_parser(
        "validate-scorecard",
        help="Validate a scorecard against the frozen suite.",
    )
    validate_parser.add_argument("--path", required=True, help="Path to the scorecard JSON file.")
    validate_parser.add_argument(
        "--allow-unscored",
        action="store_true",
        help="Allow blank dimension scores in templates.",
    )
    validate_parser.set_defaults(func=command_validate_scorecard)

    summarize_parser = subparsers.add_parser(
        "summarize-scorecard",
        help="Summarize a completed scorecard.",
    )
    summarize_parser.add_argument("--path", required=True, help="Path to the scorecard JSON file.")
    summarize_parser.add_argument("--output", help="Optional output path for the summary JSON.")
    summarize_parser.set_defaults(func=command_summarize_scorecard)

    compare_parser = subparsers.add_parser(
        "compare-scorecards",
        help="Compare multiple completed scorecards in the order provided.",
    )
    compare_parser.add_argument("paths", nargs="+", help="Scorecard JSON files to compare.")
    compare_parser.add_argument("--output", help="Optional output path for the comparison JSON.")
    compare_parser.set_defaults(func=command_compare_scorecards)

    poster_parser = subparsers.add_parser(
        "run-poster-suite",
        help="Run the deterministic poster/UI artifact suite for one git ref.",
    )
    poster_parser.add_argument("--milestone-id", help="Milestone id from milestones.yaml.")
    poster_parser.add_argument(
        "--git-ref",
        help="Explicit git ref to evaluate. Use WORKTREE to run against the current uncommitted tree.",
    )
    poster_parser.add_argument("--label", help="Human-readable label for this run.")
    poster_parser.add_argument(
        "--output-root",
        help="Directory where poster artifacts should be written.",
    )
    poster_parser.add_argument("--output-json", help="Write the JSON report to this path.")
    poster_parser.add_argument(
        "--output-markdown",
        help="Write a markdown summary to this path.",
    )
    poster_parser.set_defaults(func=command_run_poster_suite)

    compare_poster_parser = subparsers.add_parser(
        "compare-poster-runs",
        help="Compare multiple poster/UI artifact reports in the order provided.",
    )
    compare_poster_parser.add_argument(
        "paths",
        nargs="+",
        help="Poster artifact report JSON files to compare.",
    )
    compare_poster_parser.add_argument(
        "--output",
        help="Optional output path for the comparison JSON.",
    )
    compare_poster_parser.set_defaults(func=command_compare_poster_runs)

    prepare_poster_scorecard_parser = subparsers.add_parser(
        "prepare-poster-scorecard",
        help="Generate a blank manual scorecard from a poster/UI artifact report.",
    )
    prepare_poster_scorecard_parser.add_argument(
        "--report",
        required=True,
        help="Poster artifact report JSON to turn into a review template.",
    )
    prepare_poster_scorecard_parser.add_argument(
        "--output",
        required=True,
        help="Where to write the blank poster scorecard JSON.",
    )
    prepare_poster_scorecard_parser.add_argument(
        "--evaluator",
        default="human",
        help="Who will score the poster artifacts. Defaults to 'human'.",
    )
    prepare_poster_scorecard_parser.set_defaults(func=command_prepare_poster_scorecard)

    validate_poster_scorecard_parser = subparsers.add_parser(
        "validate-poster-scorecard",
        help="Validate a poster manual-review scorecard against a poster report.",
    )
    validate_poster_scorecard_parser.add_argument(
        "--path",
        required=True,
        help="Path to the poster scorecard JSON file.",
    )
    validate_poster_scorecard_parser.add_argument(
        "--report",
        required=True,
        help="Poster artifact report JSON used to seed the scorecard.",
    )
    validate_poster_scorecard_parser.add_argument(
        "--allow-unscored",
        action="store_true",
        help="Allow blank dimension scores in templates.",
    )
    validate_poster_scorecard_parser.set_defaults(func=command_validate_poster_scorecard)

    summarize_poster_scorecard_parser = subparsers.add_parser(
        "summarize-poster-scorecard",
        help="Summarize a completed poster manual-review scorecard.",
    )
    summarize_poster_scorecard_parser.add_argument(
        "--path",
        required=True,
        help="Path to the poster scorecard JSON file.",
    )
    summarize_poster_scorecard_parser.add_argument(
        "--report",
        required=True,
        help="Poster artifact report JSON used to seed the scorecard.",
    )
    summarize_poster_scorecard_parser.add_argument(
        "--output",
        help="Optional output path for the summary JSON.",
    )
    summarize_poster_scorecard_parser.set_defaults(func=command_summarize_poster_scorecard)

    compare_poster_scorecards_parser = subparsers.add_parser(
        "compare-poster-scorecards",
        help="Compare multiple completed poster manual-review scorecards.",
    )
    compare_poster_scorecards_parser.add_argument(
        "paths",
        nargs="+",
        help="Poster scorecard JSON files to compare.",
    )
    compare_poster_scorecards_parser.add_argument(
        "--reports",
        nargs="+",
        required=True,
        help="Poster artifact reports corresponding to the scorecards, in the same order.",
    )
    compare_poster_scorecards_parser.add_argument(
        "--output",
        help="Optional output path for the comparison JSON.",
    )
    compare_poster_scorecards_parser.set_defaults(func=command_compare_poster_scorecards)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
