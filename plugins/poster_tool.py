"""Hermes plugin: registers poster generation and revision tools."""
from __future__ import annotations

import json
import logging
from typing import Any

from plugins.telegram_mode_state import telegram_mode_allows
from plugins.telegram_poster_session import (
    load_poster_session_state,
    record_feedback_note,
    record_poster_result,
    resolve_reference_image_path,
)

logger = logging.getLogger(__name__)

GENERATE_POSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": (
                "Poster headline text (max ~8 words). Optional when `brief` is supplied."
            ),
        },
        "body": {
            "type": "string",
            "description": (
                "Poster body/description text (max ~220 chars). Optional when `brief` is supplied."
            ),
        },
        "brief": {
            "type": "string",
            "description": (
                "Freeform creative brief for the poster. Use this when the user gives a natural-language "
                "request rather than already-structured headline/body copy. The system will normalize it "
                "into a tighter creative brief before rendering."
            ),
        },
        "cta": {
            "type": "string",
            "description": (
                "Call-to-action button text. Leave empty to let the poster brief normalizer "
                "choose a tighter CTA and fall back to Learn More if needed."
            ),
            "default": "",
        },
        "image_prompt": {
            "type": "string",
            "description": (
                "Custom prompt for AI background image generation. "
                "If empty, auto-generated from headline + body. "
                "Include style cues like 'festive', 'corporate', 'vibrant'."
            ),
        },
        "template_name": {
            "type": "string",
            "description": "HTML template name. Leave empty to use the client default or social-post.",
            "default": "",
        },
        "image_mode": {
            "type": "string",
            "description": "AI image provider: 'openai' or 'falai'. Leave empty to use the client default.",
            "enum": ["openai", "falai"],
            "default": "",
        },
        "output_path": {
            "type": "string",
            "description": "Custom output path for poster PNG (auto-generated if empty)",
        },
        "brand_name": {
            "type": "string",
            "description": "Brand name displayed on templates that support it (optional)",
            "default": "",
        },
        "logo_mark": {
            "type": "string",
            "description": "Short logo mark text, e.g. initials (optional)",
            "default": "",
        },
        "brand_css": {
            "type": "object",
            "description": "CSS custom property overrides for brand theming",
            "default": {},
        },
        "client_id": {
            "type": "string",
            "description": "Client configuration ID for auto-theming (optional)",
            "default": "",
        },
        "style_reference": {
            "type": "string",
            "description": (
                "Optional shared style preset, e.g. 'zus-coffee', 'starbucks', "
                "'boh-tea', 'petronas', 'aesop', 'nike', or 'apple'. "
                "Use this when you want a known brand-like art direction "
                "without copying logos or taglines."
            ),
            "default": "",
        },
        "reference_image_path": {
            "type": "string",
            "description": (
                "Optional local file path to a sample poster/image. "
                "Use this when the user provides a reference visual and you "
                "want the system to follow its mood, palette, and composition."
            ),
            "default": "",
        },
        "palette": {
            "type": "object",
            "description": (
                "Color palette from search_palettes result. Pass only the color "
                "fields (primary, secondary, accent, background, text) — drop "
                "name, mood, and score."
            ),
            "properties": {
                "primary": {"type": "string"},
                "secondary": {"type": "string"},
                "accent": {"type": "string"},
                "background": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["primary", "secondary", "accent", "background", "text"],
        },
        "fonts": {
            "type": "object",
            "description": (
                "Font pairing from search_fonts result. Pass only the font "
                "fields — drop name, mood, and score."
            ),
            "properties": {
                "heading_font": {"type": "string"},
                "heading_weight": {"type": "string"},
                "body_font": {"type": "string"},
                "body_weight": {"type": "string"},
                "letter_spacing_heading": {"type": "string"},
                "letter_spacing_body": {"type": "string"},
                "line_height_heading": {"type": "string"},
                "line_height_body": {"type": "string"},
            },
            "required": [
                "heading_font",
                "heading_weight",
                "body_font",
                "body_weight",
                "letter_spacing_heading",
                "letter_spacing_body",
                "line_height_heading",
                "line_height_body",
            ],
        },
    },
    "anyOf": [
        {"required": ["brief"]},
        {"required": ["headline", "body"]},
    ],
}

_REVISION_CONTEXT_PROPERTIES = {
    "latest_poster_state": {
        "type": "object",
        "description": (
            "Optional normalized latest poster state from a prior revision tool call. "
            "Preferred for structured front-door integrations."
        ),
        "default": {},
    },
    "latest_poster_result": {
        "type": "object",
        "description": (
            "Optional latest poster result payload if the caller wants to pass prior artifact state explicitly."
        ),
        "default": {},
    },
    "latest_poster_args": {
        "type": "object",
        "description": "Optional original poster-generation args for the latest poster.",
        "default": {},
    },
    "latest_poster_path": {
        "type": "string",
        "description": "Optional explicit path to the latest poster artifact.",
        "default": "",
    },
    "latest_trace_path": {
        "type": "string",
        "description": "Optional trace JSON path for the latest poster artifact.",
        "default": "",
    },
    "latest_brief": {
        "type": "string",
        "description": "Optional prior brief text for the latest poster.",
        "default": "",
    },
    "reference_image_path": {
        "type": "string",
        "description": (
            "Optional local poster/sample reference path. If omitted, the active Telegram session reference image is reused when present."
        ),
        "default": "",
    },
    "logo_image_path": {
        "type": "string",
        "description": "Optional explicit local path to an official logo asset.",
        "default": "",
    },
    "brand_name": {
        "type": "string",
        "description": "Optional brand display name.",
        "default": "",
    },
    "logo_mark": {
        "type": "string",
        "description": "Optional text logo mark or initials.",
        "default": "",
    },
    "client_id": {
        "type": "string",
        "description": "Optional client config ID for local brand context.",
        "default": "",
    },
    "style_reference": {
        "type": "string",
        "description": "Optional style reference for mood only; this does not count as an official logo asset.",
        "default": "",
    },
    "prior_strengths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional strengths already worth preserving.",
        "default": [],
    },
    "prior_constraints": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional unresolved constraints already known by the caller.",
        "default": [],
    },
}

PREPARE_POSTER_REVISION_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback": {
            "type": "string",
            "description": (
                "Concrete poster revision feedback, such as a bigger brand mark, one main greeting only, or cleaner hierarchy."
            ),
        },
        **_REVISION_CONTEXT_PROPERTIES,
    },
    "required": ["feedback"],
}

REVISE_POSTER_STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "prepared_revision": {
            "type": "object",
            "description": "Optional full payload returned by `prepare_poster_revision`. Preferred input.",
            "default": {},
        },
        "feedback": {
            "type": "string",
            "description": "Feedback text. Optional if `prepared_revision` already includes it.",
            "default": "",
        },
        "headline": {
            "type": "string",
            "description": "Optional replacement headline if the user explicitly wants copy changes.",
            "default": "",
        },
        "body": {
            "type": "string",
            "description": "Optional replacement body copy if the user explicitly wants copy changes.",
            "default": "",
        },
        "cta": {
            "type": "string",
            "description": "Optional replacement CTA if the user explicitly wants CTA changes.",
            "default": "",
        },
        **_REVISION_CONTEXT_PROPERTIES,
    },
}

CHECK_POSTER_REVISION_SCHEMA = {
    "type": "object",
    "properties": {
        "prepared_revision": {
            "type": "object",
            "description": "Optional payload from `prepare_poster_revision`.",
            "default": {},
        },
        "revised_poster_result": {
            "type": "object",
            "description": "Optional payload from `revise_poster_structured` or legacy `revise_poster`.",
            "default": {},
        },
        "feedback": {
            "type": "string",
            "description": "Optional feedback text if the caller needs to override or restate it.",
            "default": "",
        },
        "latest_poster_state": {
            "type": "object",
            "description": "Optional normalized latest poster state for manual callers.",
            "default": {},
        },
    },
}

RESOLVE_BRAND_ASSET_SCHEMA = {
    "type": "object",
    "properties": {
        "latest_poster_state": {
            "type": "object",
            "description": "Optional latest poster state to reuse brand context from a prior tool call.",
            "default": {},
        },
        "logo_image_path": {
            "type": "string",
            "description": "Optional explicit local path to an official logo asset.",
            "default": "",
        },
        "brand_name": {
            "type": "string",
            "description": "Optional brand display name.",
            "default": "",
        },
        "logo_mark": {
            "type": "string",
            "description": "Optional text logo mark or initials.",
            "default": "",
        },
        "client_id": {
            "type": "string",
            "description": "Optional client config ID for local brand context.",
            "default": "",
        },
        "style_reference": {
            "type": "string",
            "description": "Optional style reference for art direction only.",
            "default": "",
        },
    },
}

SUMMARIZE_POSTER_REVISION_SCHEMA = {
    "type": "object",
    "properties": {
        "stage": {
            "type": "string",
            "description": "Optional stage hint: auto, prepare, revise, or check.",
            "enum": ["auto", "prepare", "revise", "check"],
            "default": "auto",
        },
        "prepared_revision": {
            "type": "object",
            "description": "Optional payload from `prepare_poster_revision`.",
            "default": {},
        },
        "revised_poster_result": {
            "type": "object",
            "description": "Optional payload from `revise_poster_structured`.",
            "default": {},
        },
        "check_result": {
            "type": "object",
            "description": "Optional payload from `check_poster_revision`.",
            "default": {},
        },
    },
}

REVISE_POSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback": {
            "type": "string",
            "description": (
                "Specific revision feedback for the latest poster in this session. "
                "Describe the concrete changes to make, such as larger brand mark, "
                "single headline, cleaner hierarchy, or better mobile readability."
            ),
        },
        "reference_image_path": {
            "type": "string",
            "description": (
                "Optional local file path to a replacement sample poster/reference image. "
                "If omitted, the active Telegram session reference image is reused when present."
            ),
            "default": "",
        },
        "headline": {
            "type": "string",
            "description": "Optional replacement headline if the user explicitly wants copy changes.",
            "default": "",
        },
        "body": {
            "type": "string",
            "description": "Optional replacement body copy if the user explicitly wants copy changes.",
            "default": "",
        },
        "cta": {
            "type": "string",
            "description": "Optional replacement CTA if the user explicitly wants CTA changes.",
            "default": "",
        },
    },
    "required": ["feedback"],
}


def _revise_poster_available() -> bool:
    state = load_poster_session_state()
    return bool(state.latest_generated_poster_path or state.latest_poster_args)


def _object_arg(args: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = args.get(key)
    if isinstance(value, dict):
        return value
    return None


def _string_list_arg(args: dict[str, Any], key: str) -> list[str] | None:
    value = args.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    return None


def _session_revision_state(args: dict[str, Any]) -> tuple[dict[str, Any], str]:
    session_state = load_poster_session_state()
    effective_reference_image_path = resolve_reference_image_path(
        str(args.get("reference_image_path", ""))
    )
    latest_state = {
        "latest_generated_poster_path": session_state.latest_generated_poster_path,
        "latest_generated_trace_path": session_state.latest_generated_trace_path,
        "latest_reference_image_path": effective_reference_image_path
        or session_state.latest_reference_image_path,
        "latest_brief": session_state.latest_brief,
        "latest_feedback_note": session_state.latest_feedback_note,
        "latest_revision_plan": session_state.latest_revision_plan,
        "latest_poster_args": session_state.latest_poster_args,
        "latest_poster_result": session_state.latest_poster_result,
        "brand_context": {
            "logo_image_path": str(args.get("logo_image_path", "")),
            "brand_name": str(args.get("brand_name", "")),
            "logo_mark": str(args.get("logo_mark", "")),
            "client_id": str(args.get("client_id", "")),
            "style_reference": str(args.get("style_reference", "")),
        },
        "prior_strengths": _string_list_arg(args, "prior_strengths") or [],
        "prior_constraints": _string_list_arg(args, "prior_constraints") or [],
    }
    return latest_state, effective_reference_image_path


def _handle_generate_poster(args: dict[str, Any], agent: Any) -> str:
    """Generate a two-layer poster and return the file path."""
    from pipelines.poster_generate import run

    headline = str(args.get("headline", ""))
    body = str(args.get("body", ""))
    brief = str(args.get("brief", ""))
    if not brief.strip() and (not headline.strip() or not body.strip()):
        return json.dumps(
            {
                "error": (
                    "headline and body are required unless brief is provided"
                )
            }
        )

    palette = args.get("palette")
    fonts = args.get("fonts")
    effective_reference_image_path = resolve_reference_image_path(
        str(args.get("reference_image_path", ""))
    )
    effective_args = dict(args)
    effective_args["reference_image_path"] = effective_reference_image_path
    try:
        result = run(
            headline=headline,
            body=body,
            brief=brief,
            cta=str(args.get("cta", "")),
            image_prompt=str(args.get("image_prompt", "")),
            template_name=str(args.get("template_name", "")),
            image_mode=str(args.get("image_mode", "")),
            output_path=str(args.get("output_path", "")),
            brand_name=str(args.get("brand_name", "")),
            logo_mark=str(args.get("logo_mark", "")),
            brand_css=args.get("brand_css") if isinstance(args.get("brand_css"), dict) else None,
            client_id=str(args.get("client_id", "")),
            style_reference=str(args.get("style_reference", "")),
            reference_image_path=effective_reference_image_path,
            palette=palette,
            fonts=fonts,
        )
        record_poster_result(
            tool_name="generate_poster",
            tool_args=effective_args,
            result_payload=result,
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("generate_poster failed")
        return json.dumps({"error": str(exc)})


def _handle_prepare_poster_revision(args: dict[str, Any], agent: Any) -> str:
    """Prepare a structured poster revision plan for front-door callers."""
    from pipelines.poster_revision import prepare_poster_revision

    feedback = str(args.get("feedback", "")).strip()
    if not feedback:
        return json.dumps({"error": "feedback is required"})

    latest_state, effective_reference_image_path = _session_revision_state(args)
    try:
        result = prepare_poster_revision(
            feedback=feedback,
            latest_poster_state=_object_arg(args, "latest_poster_state") or latest_state,
            latest_poster_result=_object_arg(args, "latest_poster_result"),
            latest_poster_args=_object_arg(args, "latest_poster_args"),
            latest_poster_path=str(args.get("latest_poster_path", "")),
            latest_trace_path=str(args.get("latest_trace_path", "")),
            latest_brief=str(args.get("latest_brief", "")),
            reference_image_path=effective_reference_image_path,
            logo_image_path=str(args.get("logo_image_path", "")),
            brand_name=str(args.get("brand_name", "")),
            logo_mark=str(args.get("logo_mark", "")),
            client_id=str(args.get("client_id", "")),
            style_reference=str(args.get("style_reference", "")),
            prior_strengths=_string_list_arg(args, "prior_strengths"),
            prior_constraints=_string_list_arg(args, "prior_constraints"),
        )
        if isinstance(result, dict) and result.get("status") == "ready":
            record_feedback_note(
                feedback,
                revision_plan=result.get("revision_plan") if isinstance(result, dict) else {},
            )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("prepare_poster_revision failed")
        return json.dumps({"error": str(exc)})


def _handle_revise_poster_structured(args: dict[str, Any], agent: Any) -> str:
    """Run the structured poster revision flow."""
    from pipelines.poster_revision import revise_poster_structured

    latest_state, effective_reference_image_path = _session_revision_state(args)
    effective_args = dict(args)
    effective_args["reference_image_path"] = effective_reference_image_path
    try:
        result = revise_poster_structured(
            prepared_revision=_object_arg(args, "prepared_revision"),
            feedback=str(args.get("feedback", "")),
            latest_poster_state=_object_arg(args, "latest_poster_state") or latest_state,
            latest_poster_result=_object_arg(args, "latest_poster_result"),
            latest_poster_args=_object_arg(args, "latest_poster_args"),
            latest_poster_path=str(args.get("latest_poster_path", "")),
            latest_trace_path=str(args.get("latest_trace_path", "")),
            latest_brief=str(args.get("latest_brief", "")),
            reference_image_path=effective_reference_image_path,
            logo_image_path=str(args.get("logo_image_path", "")),
            brand_name=str(args.get("brand_name", "")),
            logo_mark=str(args.get("logo_mark", "")),
            client_id=str(args.get("client_id", "")),
            style_reference=str(args.get("style_reference", "")),
            prior_strengths=_string_list_arg(args, "prior_strengths"),
            prior_constraints=_string_list_arg(args, "prior_constraints"),
            headline=str(args.get("headline", "")),
            body=str(args.get("body", "")),
            cta=str(args.get("cta", "")),
        )
        revision_plan = result.get("revision_plan") if isinstance(result, dict) else {}
        feedback_value = str(
            args.get("feedback")
            or (revision_plan or {}).get("feedback", "")
        ).strip()
        if feedback_value:
            record_feedback_note(feedback_value, revision_plan=revision_plan)
        if isinstance(result, dict) and result.get("status") == "revised":
            record_poster_result(
                tool_name="revise_poster_structured",
                tool_args=effective_args,
                result_payload=result,
            )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("revise_poster_structured failed")
        return json.dumps({"error": str(exc)})


def _handle_check_poster_revision(args: dict[str, Any], agent: Any) -> str:
    """Check the structured revision result with safe success semantics."""
    from pipelines.poster_revision import check_poster_revision

    latest_state, _ = _session_revision_state(args)
    try:
        result = check_poster_revision(
            prepared_revision=_object_arg(args, "prepared_revision"),
            revised_poster_result=_object_arg(args, "revised_poster_result"),
            feedback=str(args.get("feedback", "")),
            latest_poster_state=_object_arg(args, "latest_poster_state") or latest_state,
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("check_poster_revision failed")
        return json.dumps({"error": str(exc)})


def _handle_resolve_brand_asset(args: dict[str, Any], agent: Any) -> str:
    """Resolve brand asset state without claiming more than the repo can prove."""
    from pipelines.poster_revision import resolve_brand_asset

    latest_state, _ = _session_revision_state(args)
    try:
        result = resolve_brand_asset(
            latest_poster_state=_object_arg(args, "latest_poster_state") or latest_state,
            logo_image_path=str(args.get("logo_image_path", "")),
            brand_name=str(args.get("brand_name", "")),
            logo_mark=str(args.get("logo_mark", "")),
            client_id=str(args.get("client_id", "")),
            style_reference=str(args.get("style_reference", "")),
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("resolve_brand_asset failed")
        return json.dumps({"error": str(exc)})


def _handle_summarize_poster_revision(args: dict[str, Any], agent: Any) -> str:
    """Return one compact Telegram-ready summary line from structured payloads."""
    from pipelines.poster_revision import summarize_poster_revision

    try:
        result = summarize_poster_revision(
            stage=str(args.get("stage", "auto")),
            prepared_revision=_object_arg(args, "prepared_revision"),
            revised_poster_result=_object_arg(args, "revised_poster_result"),
            check_result=_object_arg(args, "check_result"),
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("summarize_poster_revision failed")
        return json.dumps({"error": str(exc)})


def _handle_revise_poster(args: dict[str, Any], agent: Any) -> str:
    """Revise the latest session poster against explicit change goals."""
    from pipelines.poster_revision import run

    feedback = str(args.get("feedback", "")).strip()
    if not feedback:
        return json.dumps({"error": "feedback is required"})

    session_state = load_poster_session_state()
    if (
        not session_state.latest_generated_poster_path
        and not session_state.latest_poster_args
    ):
        return json.dumps(
            {
                "error": (
                    "No prior poster is tracked for this session yet. "
                    "Generate a poster first, then send revision feedback."
                )
            }
        )

    effective_reference_image_path = resolve_reference_image_path(
        str(args.get("reference_image_path", ""))
    )
    record_feedback_note(feedback, revision_plan={})
    effective_args = dict(args)
    effective_args["reference_image_path"] = effective_reference_image_path
    try:
        result = run(
            feedback=feedback,
            latest_poster_state={
                "latest_generated_poster_path": session_state.latest_generated_poster_path,
                "latest_generated_trace_path": session_state.latest_generated_trace_path,
                "latest_reference_image_path": effective_reference_image_path
                or session_state.latest_reference_image_path,
                "latest_brief": session_state.latest_brief,
                "latest_poster_args": session_state.latest_poster_args,
                "latest_poster_result": session_state.latest_poster_result,
                "latest_feedback_note": session_state.latest_feedback_note,
                "latest_revision_plan": session_state.latest_revision_plan,
            },
            reference_image_path=effective_reference_image_path,
            headline=str(args.get("headline", "")),
            body=str(args.get("body", "")),
            cta=str(args.get("cta", "")),
        )
        record_feedback_note(
            feedback,
            revision_plan=result.get("revision_plan") if isinstance(result, dict) else {},
        )
        record_poster_result(
            tool_name="revise_poster",
            tool_args=effective_args,
            result_payload=result,
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("revise_poster failed")
        return json.dumps({"error": str(exc)})


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader."""
    ctx.register_tool(
        name="generate_poster",
        toolset="vizier-visual",
        schema=GENERATE_POSTER_SCHEMA,
        handler=lambda args, **kw: _handle_generate_poster(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work"),
        description=(
            "Generate a poster with AI background image + HTML text overlay. "
            "Accepts either a raw creative brief or explicit headline/body copy, and "
            "normalizes freeform briefs into tighter poster-ready direction before rendering. "
            "ALWAYS use this for poster/flyer/banner requests instead of execute_code."
        ),
    )
    ctx.register_tool(
        name="prepare_poster_revision",
        toolset="vizier-visual",
        schema=PREPARE_POSTER_REVISION_SCHEMA,
        handler=lambda args, **kw: _handle_prepare_poster_revision(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work"),
        description=(
            "Prepare a structured poster revision plan with compact Telegram-facing summaries, "
            "preserved strengths, unresolved risks, and normalized state for follow-up revision steps."
        ),
    )
    ctx.register_tool(
        name="revise_poster_structured",
        toolset="vizier-visual",
        schema=REVISE_POSTER_STRUCTURED_SCHEMA,
        handler=lambda args, **kw: _handle_revise_poster_structured(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work"),
        description=(
            "Run the structured poster revision flow using an explicit prepared revision payload or "
            "caller-supplied prior poster state. Returns revised artifact info, applied changes, "
            "and follow-up state for `check_poster_revision`."
        ),
    )
    ctx.register_tool(
        name="check_poster_revision",
        toolset="vizier-visual",
        schema=CHECK_POSTER_REVISION_SCHEMA,
        handler=lambda args, **kw: _handle_check_poster_revision(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work"),
        description=(
            "Check structured poster revision results with per-goal status, short evidence notes, "
            "and a safe Telegram-facing summary that does not overclaim visual success."
        ),
    )
    ctx.register_tool(
        name="resolve_brand_asset",
        toolset="vizier-visual",
        schema=RESOLVE_BRAND_ASSET_SCHEMA,
        handler=lambda args, **kw: _handle_resolve_brand_asset(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work"),
        description=(
            "Resolve local-first poster brand/logo asset context truthfully. "
            "Returns whether a local asset exists, whether only a text mark is available, or whether nothing is configured."
        ),
    )
    ctx.register_tool(
        name="summarize_poster_revision",
        toolset="vizier-visual",
        schema=SUMMARIZE_POSTER_REVISION_SCHEMA,
        handler=lambda args, **kw: _handle_summarize_poster_revision(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work"),
        description=(
            "Collapse structured poster revision payloads into one compact Telegram-ready summary so the front door can stay thin."
        ),
    )
    ctx.register_tool(
        name="revise_poster",
        toolset="vizier-visual",
        schema=REVISE_POSTER_SCHEMA,
        handler=lambda args, **kw: _handle_revise_poster(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work") and _revise_poster_available(),
        description=(
            "Legacy one-call poster revision entrypoint tied to the latest session poster. "
            "Prefer the prepare -> structured revise -> check sequence for new front-door integrations."
        ),
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["generate_poster"] = _handle_generate_poster
        agent._custom_agent_tools["prepare_poster_revision"] = _handle_prepare_poster_revision
        agent._custom_agent_tools["revise_poster_structured"] = _handle_revise_poster_structured
        agent._custom_agent_tools["check_poster_revision"] = _handle_check_poster_revision
        agent._custom_agent_tools["resolve_brand_asset"] = _handle_resolve_brand_asset
        agent._custom_agent_tools["summarize_poster_revision"] = _handle_summarize_poster_revision
        agent._custom_agent_tools["revise_poster"] = _handle_revise_poster
        logger.info("Poster generation and revision tools registered as agent-level tools")

    ctx.register_hook("on_agent_ready", on_agent_ready)
