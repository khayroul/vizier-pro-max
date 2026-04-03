"""Hermes plugin: registers generate_poster as an agent-level tool.

Two-layer poster generation: AI background (OpenAI/fal.ai) + HTML text
overlay via Playwright. Ported from Vizier Ultimate E4 Visual Engine.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from plugins.telegram_tool_policy import telegram_tool_allows

logger = logging.getLogger(__name__)

_SESSION_POSTER_PATH_ENV = "HERMES_TELEGRAM_POSTER_PATH"
_SESSION_POSTER_TRACE_ENV = "HERMES_TELEGRAM_POSTER_TRACE_PATH"
_SESSION_REFERENCE_IMAGE_ENV = "HERMES_TELEGRAM_REFERENCE_IMAGE_PATH"

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
                "Explicit revision feedback for the latest poster, such as "
                "'make the logo bigger', 'remove duplicate headline text', "
                "or 'clean up the layout'."
            ),
        },
        "poster_path": {
            "type": "string",
            "description": (
                "Optional local path to the poster being revised. If omitted, "
                "the current Telegram poster-session state is used when available."
            ),
            "default": "",
        },
        "trace_path": {
            "type": "string",
            "description": (
                "Optional local path to the poster trace JSON. If omitted, the "
                "Telegram poster-session trace is used when available."
            ),
            "default": "",
        },
        "reference_image_path": {
            "type": "string",
            "description": (
                "Optional local path to the latest sample/reference poster image. "
                "If omitted, the Telegram poster-session reference image is used when available."
            ),
            "default": "",
        },
        "template_name": {
            "type": "string",
            "description": "Optional explicit template override for the revision.",
            "default": "",
        },
        "brand_name": {
            "type": "string",
            "description": "Optional brand name override for the revision.",
            "default": "",
        },
        "logo_mark": {
            "type": "string",
            "description": "Optional logo mark override for the revision.",
            "default": "",
        },
        "output_path": {
            "type": "string",
            "description": "Custom output path for the revised poster PNG (auto-generated if empty).",
            "default": "",
        },
    },
    "required": ["feedback"],
}


def _session_env_default(name: str) -> str:
    return str(os.getenv(name, "")).strip()


def _telegram_front_door_enabled() -> bool:
    explicit = os.getenv("VIZIER_TELEGRAM_FRONT_DOOR", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    return bool(
        os.getenv("MESSAGING_CWD", "").strip()
        and os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )


def _revise_poster_available() -> bool:
    """Hide revise_poster on Telegram until a poster session exists."""
    if not _telegram_front_door_enabled():
        return True
    return bool(
        _session_env_default(_SESSION_POSTER_PATH_ENV)
        or _session_env_default(_SESSION_POSTER_TRACE_ENV)
    )


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
    reference_image_path = str(args.get("reference_image_path", "")).strip()
    if not reference_image_path:
        reference_image_path = _session_env_default(_SESSION_REFERENCE_IMAGE_ENV)
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
            reference_image_path=reference_image_path,
            palette=palette,
            fonts=fonts,
        )
        if result.get("poster_path"):
            result["media_tag"] = f"MEDIA:{result['poster_path']}"
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("generate_poster failed")
        return json.dumps({"error": str(exc)})


def _handle_revise_poster(args: dict[str, Any], agent: Any) -> str:
    """Revise the current poster using prior session state when available."""
    from pipelines.poster_generate import revise

    feedback = str(args.get("feedback", "")).strip()
    if not feedback:
        return json.dumps({"error": "feedback is required"})

    poster_path = str(args.get("poster_path", "")).strip() or _session_env_default(
        _SESSION_POSTER_PATH_ENV
    )
    trace_path = str(args.get("trace_path", "")).strip() or _session_env_default(
        _SESSION_POSTER_TRACE_ENV
    )
    reference_image_path = str(args.get("reference_image_path", "")).strip() or _session_env_default(
        _SESSION_REFERENCE_IMAGE_ENV
    )

    if not poster_path and not trace_path:
        return json.dumps(
            {
                "error": (
                    "No prior poster is available to revise yet. Generate a poster "
                    "first, or pass poster_path/trace_path explicitly."
                )
            }
        )

    try:
        result = revise(
            feedback=feedback,
            poster_path=poster_path,
            trace_path=trace_path,
            reference_image_path=reference_image_path,
            output_path=str(args.get("output_path", "")),
            brand_name=str(args.get("brand_name", "")),
            logo_mark=str(args.get("logo_mark", "")),
            template_name=str(args.get("template_name", "")),
        )
        if result.get("poster_path"):
            result["media_tag"] = f"MEDIA:{result['poster_path']}"
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
        check_fn=lambda: telegram_tool_allows("generate_poster"),
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
        check_fn=lambda: telegram_tool_allows("revise_poster") and _revise_poster_available(),
        description=(
            "Revise the latest poster using explicit feedback, the previous poster trace, "
            "and any Telegram session reference image. Prefer this over loosely regenerating "
            "when the user is reacting to an existing poster."
        ),
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["generate_poster"] = _handle_generate_poster
        agent._custom_agent_tools["revise_poster"] = _handle_revise_poster
        logger.info("generate_poster and revise_poster registered as agent-level tools")

    ctx.register_hook("on_agent_ready", on_agent_ready)
