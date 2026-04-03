"""Hermes plugin: registers generate_poster as an agent-level tool.

Two-layer poster generation: AI background (OpenAI/fal.ai) + HTML text
overlay via Playwright. Ported from Vizier Ultimate E4 Visual Engine.
"""
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
                "heading_font", "heading_weight", "body_font", "body_weight",
                "letter_spacing_heading", "letter_spacing_body",
                "line_height_heading", "line_height_body",
            ],
        },
    },
    "anyOf": [
        {"required": ["brief"]},
        {"required": ["headline", "body"]},
    ],
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
                **session_state.latest_poster_result,
                **{
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
        name="revise_poster",
        toolset="vizier-visual",
        schema=REVISE_POSTER_SCHEMA,
        handler=lambda args, **kw: _handle_revise_poster(args, None),
        check_fn=lambda: telegram_mode_allows("vizier_work") and _revise_poster_available(),
        description=(
            "Revise the latest poster in the current session using explicit change goals, "
            "prior poster state, and any active Telegram reference image. "
            "Use this for poster feedback and revision instead of loosely re-running generate_poster."
        ),
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["generate_poster"] = _handle_generate_poster
        agent._custom_agent_tools["revise_poster"] = _handle_revise_poster
        logger.info("generate_poster and revise_poster registered as agent-level tools")

    ctx.register_hook("on_agent_ready", on_agent_ready)
