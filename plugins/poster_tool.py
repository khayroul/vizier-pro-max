"""Hermes plugin: registers generate_poster as an agent-level tool.

Two-layer poster generation: AI background (OpenAI/fal.ai) + HTML text
overlay via Playwright. Ported from Vizier Ultimate E4 Visual Engine.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from plugins.telegram_mode_state import telegram_mode_allows

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
            reference_image_path=str(args.get("reference_image_path", "")),
            palette=palette,
            fonts=fonts,
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("generate_poster failed")
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

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["generate_poster"] = _handle_generate_poster
        logger.info("generate_poster registered as agent-level tool")

    ctx.register_hook("on_agent_ready", on_agent_ready)
