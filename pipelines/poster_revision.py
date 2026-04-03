"""Structured poster revision flow for Telegram feedback loops."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from pipelines.poster_generate import run as generate_poster


@dataclass(frozen=True)
class RevisionGoal:
    """One concrete change request compiled from user feedback."""

    key: str
    label: str
    instruction: str


@dataclass(frozen=True)
class RevisionPlan:
    """Structured poster revision plan used to drive regeneration."""

    feedback: str
    change_goals: tuple[RevisionGoal, ...]
    preserve_strengths: tuple[str, ...]
    telegram_intro: str
    telegram_summary: str
    claim_level: str = "soft"


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = _normalized_text(item)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(normalized)
    return tuple(ordered)


def _previous_creative_brief(latest_poster_state: Mapping[str, Any]) -> Mapping[str, Any]:
    latest_result = latest_poster_state.get("latest_poster_result") or {}
    creative_brief = latest_result.get("creative_brief") or {}
    if isinstance(creative_brief, Mapping):
        return creative_brief
    return {}


def _previous_tool_args(latest_poster_state: Mapping[str, Any]) -> Mapping[str, Any]:
    tool_args = latest_poster_state.get("latest_poster_args") or {}
    if isinstance(tool_args, Mapping):
        return tool_args
    return {}


def _infer_preserve_strengths(
    feedback_text: str,
    latest_poster_state: Mapping[str, Any],
) -> tuple[str, ...]:
    lowered = feedback_text.lower()
    preserves: list[str] = []
    if "festive" in lowered or "raya" in lowered:
        preserves.append("festive mood")
    if "premium" in lowered:
        preserves.append("premium feel")
    if "warm" in lowered:
        preserves.append("warm tone")
    if "readab" in lowered or "mobile" in lowered:
        preserves.append("clear readability")

    creative_brief = _previous_creative_brief(latest_poster_state)
    visual_direction = _normalized_text(creative_brief.get("visual_direction", "")).lower()
    campaign_angle = _normalized_text(creative_brief.get("campaign_angle", "")).lower()
    combined = f"{visual_direction} {campaign_angle}"
    if "festive" in combined or "raya" in combined:
        preserves.append("festive mood")
    if "premium" in combined or "luxury" in combined:
        preserves.append("premium feel")
    if "clean" in combined or "minimal" in combined:
        preserves.append("clean composition")

    return _dedupe(preserves)


def compile_revision_plan(
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any],
) -> RevisionPlan:
    """Compile natural-language feedback into explicit revision goals."""
    compact_feedback = _normalized_text(feedback)
    lowered = compact_feedback.lower()

    goals: list[RevisionGoal] = []
    if any(token in lowered for token in ("logo", "brand", "mark", "petronas", "visibility")):
        goals.append(
            RevisionGoal(
                key="brand_visibility",
                label="Stronger brand visibility",
                instruction=(
                    "Increase the logo or brand mark prominence with clearer scale, contrast, and placement."
                ),
            )
        )
    if any(
        token in lowered
        for token in ("duplicate", "single headline", "one headline", "one main", "single greeting", "main headline")
    ):
        goals.append(
            RevisionGoal(
                key="single_main_headline",
                label="One main headline only",
                instruction=(
                    "Use one clear primary greeting or headline treatment and remove duplicate headline emphasis."
                ),
            )
        )
    if any(
        token in lowered
        for token in ("clean", "hierarchy", "layout", "empty", "spacing", "premium", "organized", "balance")
    ):
        goals.append(
            RevisionGoal(
                key="cleaner_hierarchy",
                label="Cleaner hierarchy",
                instruction=(
                    "Tighten the layout hierarchy, reduce wasted space, and keep the composition premium instead of sparse."
                ),
            )
        )
    if any(token in lowered for token in ("mobile", "readable", "readability", "legible", "small text")):
        goals.append(
            RevisionGoal(
                key="mobile_readability",
                label="Stronger mobile readability",
                instruction=(
                    "Protect small-screen readability with clearer type scale, contrast, and spacing."
                ),
            )
        )
    if any(token in lowered for token in ("decorative", "busy", "clutter", "too much")):
        goals.append(
            RevisionGoal(
                key="reduce_clutter",
                label="Reduce decorative clutter",
                instruction=(
                    "Strip unnecessary decorative elements so the poster feels cleaner and more intentional."
                ),
            )
        )
    if not goals:
        goals.append(
            RevisionGoal(
                key="feedback_delta",
                label="Apply requested poster improvements",
                instruction=f"Revise the existing poster to address this feedback: {compact_feedback}",
            )
        )

    preserve_strengths = _infer_preserve_strengths(compact_feedback, latest_poster_state)
    short_goal_labels = [goal.label.lower() for goal in goals[:3]]
    telegram_intro = (
        "I’m revising "
        f"{len(goals)} thing{'s' if len(goals) != 1 else ''}: "
        + ", ".join(short_goal_labels)
        + "."
    )
    preserve_clause = ""
    if preserve_strengths:
        preserve_clause = " while keeping " + ", ".join(strength.lower() for strength in preserve_strengths[:2])
    telegram_summary = (
        "I revised the poster toward "
        + ", ".join(short_goal_labels)
        + preserve_clause
        + "."
    )
    return RevisionPlan(
        feedback=compact_feedback,
        change_goals=tuple(goals),
        preserve_strengths=preserve_strengths,
        telegram_intro=telegram_intro,
        telegram_summary=telegram_summary,
    )


def _build_revision_brief(
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any],
    plan: RevisionPlan,
) -> str:
    previous_args = _previous_tool_args(latest_poster_state)
    creative_brief = _previous_creative_brief(latest_poster_state)
    original_brief = _normalized_text(
        previous_args.get("brief")
        or creative_brief.get("raw_brief")
        or latest_poster_state.get("latest_brief", "")
    )

    parts = [
        "Revise the existing poster instead of starting from scratch.",
    ]
    if original_brief:
        parts.append(f"Original brief: {original_brief}.")
    if plan.preserve_strengths:
        parts.append(
            "Preserve: " + "; ".join(plan.preserve_strengths) + "."
        )
    parts.append(
        "Change goals: "
        + "; ".join(goal.instruction for goal in plan.change_goals)
        + "."
    )
    parts.append(
        "Use the previous poster as the baseline and keep any strengths that were not challenged by the new feedback."
    )
    parts.append(f"Latest feedback: {feedback}.")
    return " ".join(parts)


def _build_revision_output_path(previous_path: str) -> str:
    source = Path(previous_path)
    stem = source.stem or "poster"
    suffix = source.suffix or ".png"
    return str(source.with_name(f"{stem}-revision{suffix}"))


def build_revision_generate_kwargs(
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any],
    plan: RevisionPlan,
    reference_image_path: str = "",
    headline: str = "",
    body: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Build grounded generate_poster kwargs from prior poster state."""
    previous_args = dict(_previous_tool_args(latest_poster_state))
    previous_result = dict(latest_poster_state.get("latest_poster_result") or {})
    creative_brief = dict(_previous_creative_brief(latest_poster_state))

    resolved_headline = _normalized_text(
        headline
        or previous_args.get("headline")
        or creative_brief.get("headline")
    )
    resolved_body = _normalized_text(
        body
        or previous_args.get("body")
        or creative_brief.get("body")
    )
    resolved_cta = _normalized_text(
        cta
        or previous_args.get("cta")
        or creative_brief.get("cta")
    )
    prior_image_prompt = _normalized_text(
        previous_args.get("image_prompt")
        or creative_brief.get("image_prompt")
    )
    prompt_delta = " ".join(goal.instruction for goal in plan.change_goals)
    resolved_image_prompt = " ".join(
        part
        for part in (
            prior_image_prompt,
            f"Revision direction: {prompt_delta}",
        )
        if _normalized_text(part)
    ).strip()

    previous_path = _normalized_text(
        latest_poster_state.get("latest_generated_poster_path")
        or previous_result.get("poster_path")
    )

    return {
        "headline": resolved_headline,
        "body": resolved_body,
        "cta": resolved_cta,
        "brief": _build_revision_brief(
            feedback=feedback,
            latest_poster_state=latest_poster_state,
            plan=plan,
        ),
        "image_prompt": resolved_image_prompt,
        "template_name": _normalized_text(
            previous_args.get("template_name")
            or previous_result.get("template_used")
        ),
        "image_mode": _normalized_text(
            previous_args.get("image_mode")
            or previous_result.get("image_mode")
        ),
        "output_path": _build_revision_output_path(previous_path) if previous_path else "",
        "brand_name": _normalized_text(previous_args.get("brand_name")),
        "logo_mark": _normalized_text(previous_args.get("logo_mark")),
        "brand_css": previous_args.get("brand_css"),
        "client_id": _normalized_text(previous_args.get("client_id")),
        "style_reference": _normalized_text(previous_args.get("style_reference")),
        "reference_image_path": _normalized_text(
            reference_image_path
            or latest_poster_state.get("latest_reference_image_path")
            or previous_args.get("reference_image_path")
        ),
        "palette": previous_args.get("palette"),
        "fonts": previous_args.get("fonts"),
    }


def _build_self_check(plan: RevisionPlan) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for goal in plan.change_goals:
        if goal.key == "brand_visibility":
            checks.append(
                {
                    "key": goal.key,
                    "label": "Brand mark visibility targeted",
                    "status": "targeted",
                    "note": "The revision explicitly increases logo or brand mark prominence.",
                }
            )
        elif goal.key == "single_main_headline":
            checks.append(
                {
                    "key": goal.key,
                    "label": "Single main headline requested",
                    "status": "targeted",
                    "note": "The revision brief asks for one primary greeting or headline treatment only.",
                }
            )
        elif goal.key == "cleaner_hierarchy":
            checks.append(
                {
                    "key": goal.key,
                    "label": "Cleaner hierarchy requested",
                    "status": "targeted",
                    "note": "The revision brief tightens hierarchy and reduces wasted space.",
                }
            )
        elif goal.key == "mobile_readability":
            checks.append(
                {
                    "key": goal.key,
                    "label": "Mobile readability protected",
                    "status": "targeted",
                    "note": "The revision brief protects small-screen legibility.",
                }
            )
        else:
            checks.append(
                {
                    "key": goal.key,
                    "label": goal.label,
                    "status": "targeted",
                    "note": goal.instruction,
                }
            )
    return checks


def run(
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any],
    reference_image_path: str = "",
    headline: str = "",
    body: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Revise the latest poster using structured goals and prior session state."""
    latest_path = _normalized_text(latest_poster_state.get("latest_generated_poster_path"))
    previous_args = _previous_tool_args(latest_poster_state)
    if not latest_path and not previous_args:
        raise ValueError("No prior poster state is available for revision")

    plan = compile_revision_plan(
        feedback=feedback,
        latest_poster_state=latest_poster_state,
    )
    generate_kwargs = build_revision_generate_kwargs(
        feedback=feedback,
        latest_poster_state=latest_poster_state,
        plan=plan,
        reference_image_path=reference_image_path,
        headline=headline,
        body=body,
        cta=cta,
    )
    result = generate_poster(**generate_kwargs)
    payload = dict(result)
    payload["revision_plan"] = {
        "feedback": plan.feedback,
        "change_goals": [asdict(goal) for goal in plan.change_goals],
        "preserve_strengths": list(plan.preserve_strengths),
        "telegram_intro": plan.telegram_intro,
        "telegram_summary": plan.telegram_summary,
        "claim_level": plan.claim_level,
    }
    payload["revision_generate_args"] = generate_kwargs
    payload["revision_source"] = {
        "previous_poster_path": latest_path,
        "reference_image_path": generate_kwargs["reference_image_path"],
    }
    payload["self_check"] = _build_self_check(plan)
    payload["telegram_intro"] = plan.telegram_intro
    payload["telegram_summary"] = plan.telegram_summary
    payload["claim_level"] = plan.claim_level
    return payload
