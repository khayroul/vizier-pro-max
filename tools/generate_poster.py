"""generate_poster — Hermes tool for two-layer poster generation.

Registers a dedicated `generate_poster` tool so the agent reaches for it
directly instead of writing PIL code via execute_code.

Ported from Vizier Ultimate's E4 Visual Engine pattern.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _handle_generate_poster(args: dict[str, object]) -> str:
    """Thin wrapper: validate args, call pipeline, return JSON."""
    from pipelines.poster_generate import run

    headline = str(args.get("headline", ""))
    body = str(args.get("body", ""))
    if not headline or not body:
        return json.dumps({"error": "headline and body are required"})

    result = run(
        headline=headline,
        body=body,
        cta=str(args.get("cta", "Learn More")),
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
        palette=args.get("palette") if isinstance(args.get("palette"), dict) else None,
        fonts=args.get("fonts") if isinstance(args.get("fonts"), dict) else None,
    )
    return json.dumps(result, default=str)


def register_generate_poster_tool() -> None:
    """Register generate_poster with the Hermes tool registry."""
    try:
        from tools.registry import registry  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("Hermes registry not available — skipping generate_poster")
        return

    registry.register(
        name="generate_poster",
        toolset="vizier-visual",
        schema={
            "type": "object",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "Poster headline text (max ~8 words)",
                },
                "body": {
                    "type": "string",
                    "description": "Poster body/description text (max ~220 chars)",
                },
                "cta": {
                    "type": "string",
                    "description": "Call-to-action button text (default: Learn More)",
                    "default": "Learn More",
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
                    "description": "Optional shared style preset such as zus-coffee, starbucks, boh-tea, aesop, or nike.",
                    "default": "",
                },
                "reference_image_path": {
                    "type": "string",
                    "description": "Optional local file path to a sample poster/image for visual reference.",
                    "default": "",
                },
                "palette": {
                    "type": "object",
                    "description": "Optional design-intelligence palette for social-post rendering",
                },
                "fonts": {
                    "type": "object",
                    "description": "Optional design-intelligence font pairing for social-post rendering",
                },
            },
            "required": ["headline", "body"],
        },
        handler=_handle_generate_poster,
        check_fn=lambda: True,
        description=(
            "Generate a poster with AI background image + HTML text overlay. "
            "ALWAYS use this tool for poster/flyer/banner requests instead of execute_code."
        ),
    )
    logger.info("Registered generate_poster tool")
