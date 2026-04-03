"""Structured poster revision flow for Telegram feedback loops."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def _dedupe(items: Sequence[str]) -> tuple[str, ...]:
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


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return _dedupe(str(item) for item in value)
    if isinstance(value, str):
        return _dedupe(part.strip() for part in value.split("|"))
    return ()


def _load_trace_payload(trace_path: str) -> dict[str, Any]:
    path_value = _normalized_text(trace_path)
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _trace_artifact_payload(trace_payload: Mapping[str, Any]) -> dict[str, Any]:
    artifact = _mapping(trace_payload.get("artifact"))
    creative_brief = _mapping(trace_payload.get("creative_brief"))
    if not artifact:
        return {}
    payload = dict(artifact)
    if creative_brief:
        payload["creative_brief"] = creative_brief
    if artifact.get("poster_path"):
        payload["trace_path"] = str(Path(str(artifact["poster_path"])).with_suffix(".trace.json"))
    return payload


def _trace_input_payload(trace_payload: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(trace_payload.get("inputs"))


def _first_text(*values: Any) -> str:
    for value in values:
        normalized = _normalized_text(value)
        if normalized:
            return normalized
    return ""


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


def normalize_latest_poster_state(
    *,
    latest_poster_state: Mapping[str, Any] | None = None,
    latest_poster_result: Mapping[str, Any] | None = None,
    latest_poster_args: Mapping[str, Any] | None = None,
    latest_poster_path: str = "",
    latest_trace_path: str = "",
    latest_brief: str = "",
    reference_image_path: str = "",
    logo_image_path: str = "",
    brand_name: str = "",
    logo_mark: str = "",
    client_id: str = "",
    style_reference: str = "",
    prior_strengths: Sequence[str] | None = None,
    prior_constraints: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Normalize explicit caller inputs and session state into one stable payload."""
    base_state = _mapping(latest_poster_state)
    base_result = _mapping(base_state.get("latest_poster_result"))
    explicit_result = _mapping(latest_poster_result)
    base_args = _mapping(base_state.get("latest_poster_args"))
    explicit_args = _mapping(latest_poster_args)

    trace_path_value = _first_text(
        latest_trace_path,
        explicit_result.get("trace_path"),
        base_state.get("latest_generated_trace_path"),
        base_result.get("trace_path"),
    )
    trace_payload = _load_trace_payload(trace_path_value)
    trace_result = _trace_artifact_payload(trace_payload)
    trace_args = _trace_input_payload(trace_payload)

    merged_result = {**trace_result, **base_result, **explicit_result}
    merged_args = {**trace_args, **base_args, **explicit_args}

    resolved_poster_path = _first_text(
        latest_poster_path,
        merged_result.get("poster_path"),
        base_state.get("latest_generated_poster_path"),
    )
    resolved_trace_path = _first_text(
        latest_trace_path,
        merged_result.get("trace_path"),
        base_state.get("latest_generated_trace_path"),
        trace_path_value,
    )
    resolved_reference_path = _first_text(
        reference_image_path,
        base_state.get("latest_reference_image_path"),
        merged_args.get("reference_image_path"),
        trace_args.get("reference_image_path"),
    )
    resolved_brand_name = _first_text(
        brand_name,
        merged_args.get("brand_name"),
        merged_result.get("brand_name"),
    )
    resolved_logo_mark = _first_text(
        logo_mark,
        merged_args.get("logo_mark"),
        merged_result.get("logo_mark"),
    )
    resolved_client_id = _first_text(client_id, merged_args.get("client_id"))
    resolved_style_reference = _first_text(style_reference, merged_args.get("style_reference"))
    resolved_latest_brief = _first_text(
        latest_brief,
        merged_args.get("brief"),
        _mapping(merged_result.get("creative_brief")).get("raw_brief"),
        base_state.get("latest_brief"),
    )

    base_brand_context = _mapping(base_state.get("brand_context"))
    return {
        "latest_generated_poster_path": resolved_poster_path,
        "latest_generated_trace_path": resolved_trace_path,
        "latest_reference_image_path": resolved_reference_path,
        "latest_brief": resolved_latest_brief,
        "latest_feedback_note": _first_text(base_state.get("latest_feedback_note")),
        "latest_revision_plan": _mapping(base_state.get("latest_revision_plan")),
        "latest_poster_args": merged_args,
        "latest_poster_result": merged_result,
        "brand_context": {
            "brand_name": resolved_brand_name,
            "logo_mark": resolved_logo_mark,
            "client_id": resolved_client_id,
            "style_reference": resolved_style_reference,
            "logo_image_path": _first_text(
                logo_image_path,
                base_brand_context.get("logo_image_path"),
            ),
        },
        "prior_strengths": list(
            _dedupe(
                [
                    *_string_tuple(base_state.get("prior_strengths")),
                    *list(prior_strengths or ()),
                ]
            )
        ),
        "prior_constraints": list(
            _dedupe(
                [
                    *_string_tuple(base_state.get("prior_constraints")),
                    *list(prior_constraints or ()),
                ]
            )
        ),
    }


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
        for token in (
            "duplicate",
            "single headline",
            "one headline",
            "one main",
            "single greeting",
            "main headline",
        )
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
        parts.append("Preserve: " + "; ".join(plan.preserve_strengths) + ".")
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
    brand_context = _mapping(latest_poster_state.get("brand_context"))

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
        "brand_name": _first_text(
            brand_context.get("brand_name"),
            previous_args.get("brand_name"),
            previous_result.get("brand_name"),
        ),
        "logo_mark": _first_text(
            brand_context.get("logo_mark"),
            previous_args.get("logo_mark"),
            previous_result.get("logo_mark"),
        ),
        "brand_css": previous_args.get("brand_css"),
        "client_id": _first_text(brand_context.get("client_id"), previous_args.get("client_id")),
        "style_reference": _first_text(
            brand_context.get("style_reference"),
            previous_args.get("style_reference"),
        ),
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


def resolve_brand_asset(
    *,
    latest_poster_state: Mapping[str, Any] | None = None,
    logo_image_path: str = "",
    brand_name: str = "",
    logo_mark: str = "",
    client_id: str = "",
    style_reference: str = "",
) -> dict[str, Any]:
    """Resolve brand/logo context without overstating local asset availability."""
    state = normalize_latest_poster_state(
        latest_poster_state=latest_poster_state,
        logo_image_path=logo_image_path,
        brand_name=brand_name,
        logo_mark=logo_mark,
        client_id=client_id,
        style_reference=style_reference,
    )
    brand_context = _mapping(state.get("brand_context"))
    resolved_brand_name = _normalized_text(brand_context.get("brand_name"))
    resolved_logo_mark = _normalized_text(brand_context.get("logo_mark"))
    resolved_client_id = _normalized_text(brand_context.get("client_id"))
    resolved_style_reference = _normalized_text(brand_context.get("style_reference"))
    explicit_logo_path = _normalized_text(brand_context.get("logo_image_path"))

    if resolved_client_id:
        from config.client_loader import load_client

        client = load_client(resolved_client_id)
        if client is not None:
            resolved_brand_name = resolved_brand_name or client.client_name
            resolved_logo_mark = resolved_logo_mark or client.brand.logo_mark

    notes: list[str] = []
    if explicit_logo_path:
        path = Path(explicit_logo_path)
        if path.is_file():
            notes.append("Using the caller-provided local logo asset.")
            if resolved_style_reference:
                notes.append("Style reference metadata is art direction only, not logo provenance.")
            return {
                "status": "found_local_asset",
                "asset_path": str(path),
                "brand_name": resolved_brand_name,
                "logo_mark": resolved_logo_mark,
                "notes": notes,
                "provenance": "explicit_local_path",
            }
        notes.append(f"Provided logo_image_path was not found locally: {explicit_logo_path}")

    if resolved_brand_name or resolved_logo_mark:
        if resolved_client_id:
            notes.append("Client config provides text-based brand context only; no local official logo asset is configured.")
        else:
            notes.append("Only a text brand name or logo_mark is available locally.")
        if resolved_style_reference:
            notes.append("Style reference metadata does not count as an official logo asset.")
        return {
            "status": "text_mark_only",
            "asset_path": "",
            "brand_name": resolved_brand_name,
            "logo_mark": resolved_logo_mark,
            "notes": notes,
            "provenance": "client_config_text_mark" if resolved_client_id else "caller_text_mark",
        }

    notes.append("No local logo asset or text mark is available.")
    if resolved_style_reference:
        notes.append("Style reference metadata does not count as an official logo asset.")
    return {
        "status": "unavailable",
        "asset_path": "",
        "brand_name": resolved_brand_name,
        "logo_mark": resolved_logo_mark,
        "notes": notes,
        "provenance": "none",
    }


def _logo_runtime_constraints(asset_status: Mapping[str, Any]) -> tuple[str, ...]:
    status = _normalized_text(asset_status.get("status"))
    if status == "found_local_asset":
        return (
            "A local logo asset exists, but the current poster runtime still renders text-based logo_mark surfaces unless downstream image-logo support is added.",
        )
    if status == "text_mark_only":
        return (
            "Only a text logo_mark is available locally; no official logo asset is configured yet.",
        )
    return ("No local brand asset is available yet for stronger logo treatment.",)


def _plan_payload(
    plan: RevisionPlan,
    *,
    preserve_strengths: Sequence[str],
    unresolved_risks: Sequence[str],
    asset_status: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "feedback": plan.feedback,
        "change_goals": [asdict(goal) for goal in plan.change_goals],
        "preserve_strengths": list(_dedupe(preserve_strengths)),
        "unresolved_risks": list(_dedupe(unresolved_risks)),
        "asset_status": dict(asset_status),
        "telegram_intro": plan.telegram_intro,
        "telegram_summary": plan.telegram_summary,
        "claim_level": plan.claim_level,
    }


def _plan_from_payload(
    plan_payload: Mapping[str, Any] | None,
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any],
) -> RevisionPlan:
    payload = _mapping(plan_payload)
    goals_payload = payload.get("change_goals")
    goals: list[RevisionGoal] = []
    if isinstance(goals_payload, list):
        for item in goals_payload:
            item_mapping = _mapping(item)
            key = _normalized_text(item_mapping.get("key"))
            label = _normalized_text(item_mapping.get("label"))
            instruction = _normalized_text(item_mapping.get("instruction"))
            if key and label and instruction:
                goals.append(
                    RevisionGoal(
                        key=key,
                        label=label,
                        instruction=instruction,
                    )
                )
    if not goals:
        return compile_revision_plan(
            feedback=feedback,
            latest_poster_state=latest_poster_state,
        )
    return RevisionPlan(
        feedback=_first_text(payload.get("feedback"), feedback),
        change_goals=tuple(goals),
        preserve_strengths=_dedupe(payload.get("preserve_strengths", ())),
        telegram_intro=_first_text(payload.get("telegram_intro"), "I’m revising the poster."),
        telegram_summary=_first_text(payload.get("telegram_summary"), "I revised the poster."),
        claim_level=_first_text(payload.get("claim_level"), "soft"),
    )


def prepare_poster_revision(
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any] | None = None,
    latest_poster_result: Mapping[str, Any] | None = None,
    latest_poster_args: Mapping[str, Any] | None = None,
    latest_poster_path: str = "",
    latest_trace_path: str = "",
    latest_brief: str = "",
    reference_image_path: str = "",
    logo_image_path: str = "",
    brand_name: str = "",
    logo_mark: str = "",
    client_id: str = "",
    style_reference: str = "",
    prior_strengths: Sequence[str] | None = None,
    prior_constraints: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compile revision goals plus caller-safe state for a later revision step."""
    normalized_state = normalize_latest_poster_state(
        latest_poster_state=latest_poster_state,
        latest_poster_result=latest_poster_result,
        latest_poster_args=latest_poster_args,
        latest_poster_path=latest_poster_path,
        latest_trace_path=latest_trace_path,
        latest_brief=latest_brief,
        reference_image_path=reference_image_path,
        logo_image_path=logo_image_path,
        brand_name=brand_name,
        logo_mark=logo_mark,
        client_id=client_id,
        style_reference=style_reference,
        prior_strengths=prior_strengths,
        prior_constraints=prior_constraints,
    )
    compact_feedback = _normalized_text(feedback)
    asset_status = resolve_brand_asset(latest_poster_state=normalized_state)
    previous_args = _previous_tool_args(normalized_state)
    if not normalized_state.get("latest_generated_poster_path") and not previous_args:
        unresolved_risks = _dedupe(
            [
                *normalized_state.get("prior_constraints", []),
                "Need the latest poster result, path, or args before a grounded revision can be prepared.",
            ]
        )
        return {
            "status": "missing_prior_poster",
            "feedback": compact_feedback,
            "goals": [],
            "preserve_strengths": list(_string_tuple(normalized_state.get("prior_strengths"))),
            "unresolved_risks": list(unresolved_risks),
            "asset_status": asset_status,
            "latest_poster_state": normalized_state,
            "revision_plan": {
                "feedback": compact_feedback,
                "change_goals": [],
                "preserve_strengths": list(_string_tuple(normalized_state.get("prior_strengths"))),
                "unresolved_risks": list(unresolved_risks),
                "asset_status": asset_status,
                "telegram_intro": "I need the latest poster before I can prepare a grounded revision.",
                "telegram_summary": "I need the latest poster before I can prepare a grounded revision.",
                "claim_level": "soft",
            },
            "telegram_summary": "I need the latest poster before I can prepare a grounded revision.",
            "claim_level": "soft",
            "next_step": "generate_poster",
        }

    plan = compile_revision_plan(
        feedback=compact_feedback,
        latest_poster_state=normalized_state,
    )
    preserve_strengths = _dedupe(
        [*plan.preserve_strengths, *normalized_state.get("prior_strengths", [])]
    )
    unresolved_risks = list(normalized_state.get("prior_constraints", []))
    if any(goal.key == "brand_visibility" for goal in plan.change_goals):
        unresolved_risks.extend(_logo_runtime_constraints(asset_status))

    plan_payload = _plan_payload(
        plan,
        preserve_strengths=preserve_strengths,
        unresolved_risks=unresolved_risks,
        asset_status=asset_status,
    )
    return {
        "status": "ready",
        "feedback": plan.feedback,
        "goals": plan_payload["change_goals"],
        "preserve_strengths": plan_payload["preserve_strengths"],
        "unresolved_risks": plan_payload["unresolved_risks"],
        "asset_status": asset_status,
        "latest_poster_state": normalized_state,
        "revision_plan": plan_payload,
        "telegram_summary": plan.telegram_intro,
        "claim_level": plan.claim_level,
        "next_step": "revise_poster_structured",
    }


def _applied_change_entries(
    plan: RevisionPlan,
    *,
    asset_status: Mapping[str, Any],
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for goal in plan.change_goals:
        note = "Applied to the revision brief and regeneration step."
        if goal.key == "brand_visibility":
            if _normalized_text(asset_status.get("status")) == "text_mark_only":
                note = "Applied with text-based brand context; no official logo asset is configured locally."
            elif _normalized_text(asset_status.get("status")) == "found_local_asset":
                note = "Applied with local brand context available, but current poster templates still rely on text-based logo_mark surfaces."
            else:
                note = "Applied to the revision brief, but brand visibility is still constrained by missing local brand assets."
        entries.append(
            {
                "key": goal.key,
                "label": goal.label,
                "status": "applied",
                "note": note,
            }
        )
    return entries


def _artifact_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping(result)
    return {
        "poster_path": _normalized_text(payload.get("poster_path")),
        "hero_path": _normalized_text(payload.get("hero_path")),
        "trace_path": _normalized_text(payload.get("trace_path")),
        "template_used": _normalized_text(payload.get("template_used")),
        "image_mode": _normalized_text(payload.get("image_mode")),
        "width": payload.get("width"),
        "height": payload.get("height"),
    }


def revise_poster_structured(
    *,
    prepared_revision: Mapping[str, Any] | None = None,
    feedback: str = "",
    latest_poster_state: Mapping[str, Any] | None = None,
    latest_poster_result: Mapping[str, Any] | None = None,
    latest_poster_args: Mapping[str, Any] | None = None,
    latest_poster_path: str = "",
    latest_trace_path: str = "",
    latest_brief: str = "",
    reference_image_path: str = "",
    logo_image_path: str = "",
    brand_name: str = "",
    logo_mark: str = "",
    client_id: str = "",
    style_reference: str = "",
    prior_strengths: Sequence[str] | None = None,
    prior_constraints: Sequence[str] | None = None,
    headline: str = "",
    body: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Run the structured poster revision flow and return a stable payload."""
    prepared = _mapping(prepared_revision)
    if not prepared:
        prepared = prepare_poster_revision(
            feedback=feedback,
            latest_poster_state=latest_poster_state,
            latest_poster_result=latest_poster_result,
            latest_poster_args=latest_poster_args,
            latest_poster_path=latest_poster_path,
            latest_trace_path=latest_trace_path,
            latest_brief=latest_brief,
            reference_image_path=reference_image_path,
            logo_image_path=logo_image_path,
            brand_name=brand_name,
            logo_mark=logo_mark,
            client_id=client_id,
            style_reference=style_reference,
            prior_strengths=prior_strengths,
            prior_constraints=prior_constraints,
        )
    if _normalized_text(prepared.get("status")) != "ready":
        return dict(prepared)

    normalized_state = normalize_latest_poster_state(
        latest_poster_state=prepared.get("latest_poster_state"),
        reference_image_path=reference_image_path,
        logo_image_path=logo_image_path,
        brand_name=brand_name,
        logo_mark=logo_mark,
        client_id=client_id,
        style_reference=style_reference,
    )
    plan_payload = _mapping(prepared.get("revision_plan"))
    plan = _plan_from_payload(
        plan_payload,
        feedback=_first_text(prepared.get("feedback"), feedback),
        latest_poster_state=normalized_state,
    )
    asset_status = _mapping(prepared.get("asset_status")) or resolve_brand_asset(
        latest_poster_state=normalized_state
    )

    generate_kwargs = build_revision_generate_kwargs(
        feedback=plan.feedback,
        latest_poster_state=normalized_state,
        plan=plan,
        reference_image_path=_first_text(
            reference_image_path,
            normalized_state.get("latest_reference_image_path"),
        ),
        headline=headline,
        body=body,
        cta=cta,
    )
    result = generate_poster(**generate_kwargs)
    payload = dict(result)
    artifact = _artifact_payload(payload)
    self_check = _build_self_check(plan)
    unresolved_constraints = _dedupe(
        [
            *_string_tuple(plan_payload.get("unresolved_risks")),
            *normalized_state.get("prior_constraints", []),
        ]
    )
    follow_up_state = normalize_latest_poster_state(
        latest_poster_state=normalized_state,
        latest_poster_result=payload,
        latest_poster_args=generate_kwargs,
        latest_poster_path=artifact["poster_path"],
        latest_trace_path=artifact["trace_path"],
        latest_brief=generate_kwargs.get("brief", ""),
        reference_image_path=generate_kwargs.get("reference_image_path", ""),
        logo_image_path=_mapping(normalized_state.get("brand_context")).get("logo_image_path", ""),
        brand_name=generate_kwargs.get("brand_name", ""),
        logo_mark=generate_kwargs.get("logo_mark", ""),
        client_id=generate_kwargs.get("client_id", ""),
        style_reference=generate_kwargs.get("style_reference", ""),
        prior_strengths=plan_payload.get("preserve_strengths", []),
        prior_constraints=unresolved_constraints,
    )
    payload["status"] = "revised"
    payload["artifact"] = artifact
    payload["revision_plan"] = _plan_payload(
        plan,
        preserve_strengths=plan_payload.get("preserve_strengths", plan.preserve_strengths),
        unresolved_risks=unresolved_constraints,
        asset_status=asset_status,
    )
    payload["revision_generate_args"] = generate_kwargs
    payload["revision_source"] = {
        "previous_poster_path": _normalized_text(
            normalized_state.get("latest_generated_poster_path")
        ),
        "previous_trace_path": _normalized_text(
            normalized_state.get("latest_generated_trace_path")
        ),
        "reference_image_path": generate_kwargs["reference_image_path"],
    }
    payload["applied_changes"] = _applied_change_entries(plan, asset_status=asset_status)
    payload["unresolved_constraints"] = list(unresolved_constraints)
    payload["asset_status"] = asset_status
    payload["latest_poster_state"] = follow_up_state
    payload["self_check"] = self_check
    payload["telegram_intro"] = plan.telegram_intro
    payload["telegram_summary"] = plan.telegram_summary
    payload["claim_level"] = plan.claim_level
    payload["next_step"] = "check_poster_revision"
    return payload


def _goal_check_entry(
    goal: RevisionGoal,
    *,
    revised_poster_result: Mapping[str, Any],
    asset_status: Mapping[str, Any],
) -> dict[str, str]:
    creative_brief = _mapping(revised_poster_result.get("creative_brief"))
    revision_generate_args = _mapping(revised_poster_result.get("revision_generate_args"))
    artifact = _artifact_payload(revised_poster_result)

    if goal.key == "brand_visibility":
        logo_mark = _first_text(
            revised_poster_result.get("logo_mark"),
            revision_generate_args.get("logo_mark"),
            asset_status.get("logo_mark"),
        )
        if logo_mark:
            note = f"Revision regenerated the poster with logo_mark '{logo_mark}'."
            if _normalized_text(asset_status.get("status")) != "found_local_asset":
                note += " Official logo usage still depends on a provided local asset."
            return {
                "key": goal.key,
                "label": goal.label,
                "status": "supported",
                "evidence": note,
            }
        return {
            "key": goal.key,
            "label": goal.label,
            "status": "blocked",
            "evidence": "No local brand asset or text logo_mark was available to strengthen brand visibility.",
        }
    if goal.key == "single_main_headline":
        headline = _first_text(
            creative_brief.get("headline"),
            revision_generate_args.get("headline"),
        )
        if headline:
            return {
                "key": goal.key,
                "label": goal.label,
                "status": "supported",
                "evidence": f"Revision output carries one primary headline slot: '{headline}'.",
            }
    if goal.key == "cleaner_hierarchy":
        return {
            "key": goal.key,
            "label": goal.label,
            "status": "targeted",
            "evidence": (
                "Revision regenerated the poster with explicit hierarchy-tightening instructions "
                f"and a new artifact at {artifact['poster_path']}."
            ),
        }
    if goal.key == "mobile_readability":
        return {
            "key": goal.key,
            "label": goal.label,
            "status": "targeted",
            "evidence": "Revision brief explicitly protects small-screen readability, but visual confirmation still needs human review.",
        }
    if goal.key == "reduce_clutter":
        return {
            "key": goal.key,
            "label": goal.label,
            "status": "targeted",
            "evidence": "Revision brief explicitly removes decorative clutter, but visual confirmation still needs human review.",
        }
    return {
        "key": goal.key,
        "label": goal.label,
        "status": "targeted",
        "evidence": goal.instruction,
    }


def _check_overall_status(goal_statuses: Sequence[Mapping[str, Any]]) -> str:
    statuses = {_normalized_text(goal.get("status")) for goal in goal_statuses}
    if "blocked" in statuses:
        return "partially_blocked"
    if statuses and statuses <= {"supported"}:
        return "supported_with_review"
    return "needs_visual_review"


def _check_summary(
    goal_statuses: Sequence[Mapping[str, Any]],
    *,
    asset_status: Mapping[str, Any],
) -> str:
    phrases: list[str] = []
    for goal in goal_statuses:
        key = _normalized_text(goal.get("key"))
        status = _normalized_text(goal.get("status"))
        if key == "brand_visibility" and status in {"supported", "targeted"}:
            phrases.append("I increased the logo emphasis")
        elif key == "single_main_headline" and status in {"supported", "targeted"}:
            phrases.append("I kept the poster to one main headline")
        elif key == "cleaner_hierarchy" and status in {"supported", "targeted"}:
            phrases.append("I tightened the hierarchy")
        elif key == "mobile_readability" and status in {"supported", "targeted"}:
            phrases.append("I protected mobile readability")
    if not phrases:
        phrases.append("I applied the requested revision goals")

    summary = ", ".join(phrases[:2])
    if len(phrases) > 2:
        summary += ", and " + phrases[2]
    summary = summary[0].upper() + summary[1:] + "."

    asset_state = _normalized_text(asset_status.get("status"))
    if asset_state == "text_mark_only":
        summary += " The official logo still depends on a provided local asset."
    elif asset_state == "found_local_asset":
        summary += " A local logo asset is available, but current poster templates still rely on text-based logo_mark surfaces."
    elif asset_state == "unavailable":
        summary += " Stronger brand treatment is still limited by missing local brand assets."
    return summary


def check_poster_revision(
    *,
    prepared_revision: Mapping[str, Any] | None = None,
    revised_poster_result: Mapping[str, Any] | None = None,
    feedback: str = "",
    latest_poster_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a safe, Telegram-friendly revision check summary."""
    prepared = _mapping(prepared_revision)
    revised = _mapping(revised_poster_result)
    state_source = _mapping(revised.get("latest_poster_state")) or _mapping(
        prepared.get("latest_poster_state")
    ) or _mapping(latest_poster_state)
    normalized_state = normalize_latest_poster_state(latest_poster_state=state_source)
    plan_payload = _mapping(revised.get("revision_plan")) or _mapping(prepared.get("revision_plan"))
    plan = _plan_from_payload(
        plan_payload,
        feedback=_first_text(
            feedback,
            revised.get("feedback"),
            prepared.get("feedback"),
            normalized_state.get("latest_feedback_note"),
        ),
        latest_poster_state=normalized_state,
    )
    asset_status = _mapping(revised.get("asset_status")) or _mapping(
        plan_payload.get("asset_status")
    ) or resolve_brand_asset(latest_poster_state=normalized_state)
    goal_statuses = [
        _goal_check_entry(
            goal,
            revised_poster_result=revised,
            asset_status=asset_status,
        )
        for goal in plan.change_goals
    ]
    overall_status = _check_overall_status(goal_statuses)
    unresolved_constraints = list(
        _dedupe(
            [
                *_string_tuple(revised.get("unresolved_constraints")),
                *_string_tuple(plan_payload.get("unresolved_risks")),
            ]
        )
    )
    telegram_summary = _check_summary(goal_statuses, asset_status=asset_status)
    return {
        "status": "checked",
        "overall_status": overall_status,
        "goal_statuses": goal_statuses,
        "unresolved_constraints": unresolved_constraints,
        "asset_status": asset_status,
        "telegram_summary": telegram_summary,
        "claim_level": _first_text(revised.get("claim_level"), plan.claim_level, "soft"),
        "artifact": _artifact_payload(revised),
    }


def summarize_poster_revision(
    *,
    stage: str = "",
    prepared_revision: Mapping[str, Any] | None = None,
    revised_poster_result: Mapping[str, Any] | None = None,
    check_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert structured revision payloads into one compact caller-facing summary."""
    normalized_stage = _normalized_text(stage).lower()
    check_payload = _mapping(check_result)
    revised_payload = _mapping(revised_poster_result)
    prepared_payload = _mapping(prepared_revision)

    if normalized_stage in {"", "auto", "check"} and check_payload:
        return {
            "status": "summarized",
            "stage": "check",
            "telegram_summary": _first_text(check_payload.get("telegram_summary")),
            "claim_level": _first_text(check_payload.get("claim_level"), "soft"),
        }
    if normalized_stage in {"", "auto", "revise"} and revised_payload:
        return {
            "status": "summarized",
            "stage": "revise",
            "telegram_summary": _first_text(revised_payload.get("telegram_summary")),
            "claim_level": _first_text(revised_payload.get("claim_level"), "soft"),
        }
    if prepared_payload:
        return {
            "status": "summarized",
            "stage": "prepare",
            "telegram_summary": _first_text(prepared_payload.get("telegram_summary")),
            "claim_level": _first_text(prepared_payload.get("claim_level"), "soft"),
        }
    return {
        "status": "summarized",
        "stage": normalized_stage or "unknown",
        "telegram_summary": "",
        "claim_level": "soft",
    }


def run(
    *,
    feedback: str,
    latest_poster_state: Mapping[str, Any],
    reference_image_path: str = "",
    headline: str = "",
    body: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Legacy single-call revision wrapper preserved for existing callers."""
    normalized_state = normalize_latest_poster_state(
        latest_poster_state=latest_poster_state,
        reference_image_path=reference_image_path,
    )
    latest_path = _normalized_text(normalized_state.get("latest_generated_poster_path"))
    previous_args = _previous_tool_args(normalized_state)
    if not latest_path and not previous_args:
        raise ValueError("No prior poster state is available for revision")

    prepared = prepare_poster_revision(
        feedback=feedback,
        latest_poster_state=normalized_state,
        reference_image_path=reference_image_path,
    )
    revised = revise_poster_structured(
        prepared_revision=prepared,
        headline=headline,
        body=body,
        cta=cta,
    )
    revised["prepared_revision"] = prepared
    revised["check_result"] = check_poster_revision(
        prepared_revision=prepared,
        revised_poster_result=revised,
    )
    return revised
