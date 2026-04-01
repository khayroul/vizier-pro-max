"""Hermes plugin: registers generate_poster as an agent-level tool.

Two-layer poster generation: AI background (OpenAI/fal.ai) + HTML text
overlay via Playwright. Ported from Vizier Ultimate E4 Visual Engine.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

GENERATE_POSTER_SCHEMA = {
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
            "description": "HTML template name (default: social-post)",
            "default": "social-post",
        },
        "image_mode": {
            "type": "string",
            "description": "AI image provider: 'openai' or 'falai'",
            "enum": ["openai", "falai"],
            "default": "openai",
        },
        "output_path": {
            "type": "string",
            "description": "Custom output path for poster PNG (auto-generated if empty)",
        },
    },
    "required": ["headline", "body"],
}


def _handle_generate_poster(args: dict[str, Any], agent: Any) -> str:
    """Generate a two-layer poster and return the file path."""
    from pipelines.poster_generate import run

    headline = str(args.get("headline", ""))
    body = str(args.get("body", ""))
    if not headline or not body:
        return json.dumps({"error": "headline and body are required"})

    try:
        result = run(
            headline=headline,
            body=body,
            cta=str(args.get("cta", "Learn More")),
            image_prompt=str(args.get("image_prompt", "")),
            template_name=str(args.get("template_name", "social-post")),
            image_mode=str(args.get("image_mode", "openai")),
            output_path=str(args.get("output_path", "")),
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
        check_fn=lambda: True,
        description=(
            "Generate a poster with AI background image + HTML text overlay. "
            "ALWAYS use this for poster/flyer/banner requests instead of execute_code."
        ),
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["generate_poster"] = _handle_generate_poster
        logger.info("generate_poster registered as agent-level tool")

    ctx.register_hook("on_agent_ready", on_agent_ready)
