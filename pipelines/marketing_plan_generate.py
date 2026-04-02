"""Marketing-plan orchestrator from brief to strategy and creative package."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog

from adapter.llm_client import chat as llm_chat
from config.client_loader import load_client
from pipelines.longform.spine import slugify
from pipelines.structured_nonfiction_generate import run as run_structured_nonfiction

logger = structlog.get_logger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM_PROMPT = """
You create concise, commercially useful marketing plans for SMEs.
Return ONLY valid JSON with this exact top-level shape:
{
  "title": "string",
  "subtitle": "string",
  "strategy": {
    "objective": "string",
    "audience": "string",
    "offer": "string",
    "positioning": "string",
    "key_message": "string",
    "market_context": "string",
    "budget": "string",
    "timeline": "string",
    "primary_cta": "string",
    "channels": ["string"],
    "kpis": ["string"],
    "constraints": ["string"],
    "recommended_actions": ["string"]
  },
  "campaign_angles": [
    {
      "name": "string",
      "audience_segment": "string",
      "pain_point": "string",
      "promise": "string",
      "proof": "string",
      "message": "string",
      "offer": "string",
      "cta": "string",
      "channels": ["string"],
      "visual_direction": "string",
      "headline": "string",
      "body": "string",
      "notes": "string",
      "score": 0
    }
  ],
  "creative_variants": [
    {
      "angle_name": "string",
      "channel": "string",
      "headline": "string",
      "body": "string",
      "cta": "string",
      "image_prompt": "string",
      "notes": "string",
      "score": 0
    }
  ],
  "content_calendar": [
    {
      "period": "string",
      "channel": "string",
      "deliverable": "string",
      "theme": "string",
      "cta": "string",
      "notes": "string"
    }
  ],
  "sections": [
    {
      "heading": "string",
      "body": "string"
    }
  ]
}

Rules:
- Be practical, concrete, and client-ready.
- Produce 3 campaign_angles with distinct positioning.
- Produce 1 creative_variant per campaign angle.
- Keep scores between 1 and 10.
- Keep content_calendar to 4 entries max.
- No markdown fences, no commentary, no extra keys.
""".strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from model output."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(candidate)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _derive_title(brief: str, client_name: str = "") -> str:
    """Derive a stable title when one is not provided."""
    words = [word.strip(" ,.:;!?") for word in brief.split() if word.strip(" ,.:;!?")]
    stem = " ".join(words[:6]).title() if words else "Marketing Plan"
    if client_name:
        return f"{client_name} Campaign Plan"
    if stem:
        return f"{stem} Marketing Plan"
    return "Marketing Plan"


def _fallback_plan(
    *,
    brief: str,
    title: str,
) -> dict[str, Any]:
    """Build a deterministic fallback plan when no LLM is available."""
    base_offer = "Clarify the offer and turn it into channel-ready creative."
    return {
        "title": title,
        "subtitle": "Strategy plan and creative pack",
        "strategy": {
            "objective": brief,
            "audience": "Prospects described in the brief.",
            "offer": base_offer,
            "positioning": "Useful, specific, and easy to act on.",
            "key_message": "Move quickly from strategy into deployable assets.",
            "market_context": brief,
            "budget": "To be confirmed with the client.",
            "timeline": "4-week campaign sprint.",
            "primary_cta": "Contact us to launch",
            "channels": ["Meta Ads", "Instagram", "WhatsApp"],
            "kpis": ["Qualified leads", "Click-through rate", "Conversion rate"],
            "constraints": ["Need brand-safe creative", "Need fast execution"],
            "recommended_actions": [
                "Test three campaign angles in week one.",
                "Promote the strongest angle across paid and organic channels.",
                "Retarget warm audiences with a clear CTA.",
            ],
        },
        "campaign_angles": [
            {
                "name": "Offer Clarity",
                "audience_segment": "People who are interested but undecided.",
                "pain_point": "They do not yet understand the offer clearly.",
                "promise": "Make the offer easier to trust and act on.",
                "proof": "Use direct, benefit-led messaging and simple proof points.",
                "message": "Explain the offer in plain, useful language.",
                "offer": base_offer,
                "cta": "Contact us to launch",
                "channels": ["Meta Ads", "Instagram"],
                "visual_direction": "Clean, premium layout with a single focal product.",
                "headline": "Make The Offer Easy To Say Yes To",
                "body": "Clarify the value, remove friction, and give buyers one clear next step.",
                "notes": "Best for broad prospecting.",
                "score": 8.6,
            },
            {
                "name": "Problem Solution",
                "audience_segment": "People actively feeling the problem now.",
                "pain_point": "They need a faster path to a good outcome.",
                "promise": "Show how the offer removes a real bottleneck.",
                "proof": "Tie the message directly to a practical result.",
                "message": "Lead with the pain point, then show the solution.",
                "offer": base_offer,
                "cta": "Book a quick consult",
                "channels": ["Meta Ads", "WhatsApp"],
                "visual_direction": "Urgent but polished, with strong contrast and action cues.",
                "headline": "Solve The Bottleneck Faster",
                "body": "Highlight the problem, show the relief, and make the next action obvious.",
                "notes": "Best for high-intent audiences.",
                "score": 8.2,
            },
            {
                "name": "Trust Builder",
                "audience_segment": "People who need reassurance before buying.",
                "pain_point": "They are unsure if the offer will deliver.",
                "promise": "Increase confidence with proof and clear outcomes.",
                "proof": "Use testimonials, specifics, and outcome framing.",
                "message": "Build trust before asking for action.",
                "offer": base_offer,
                "cta": "See how it works",
                "channels": ["Instagram", "WhatsApp"],
                "visual_direction": "Editorial, proof-led creative with credible details.",
                "headline": "Give Buyers A Reason To Trust",
                "body": "Lead with confidence signals and pair them with a low-friction CTA.",
                "notes": "Best for warmer audiences.",
                "score": 7.9,
            },
        ],
        "creative_variants": [],
        "content_calendar": [
            {
                "period": "Week 1",
                "channel": "Meta Ads",
                "deliverable": "Angle testing posters and copy",
                "theme": "Offer Clarity",
                "cta": "Contact us to launch",
                "notes": "Test all three angles with equal spend.",
            },
            {
                "period": "Week 2",
                "channel": "Instagram",
                "deliverable": "Organic carousel and story set",
                "theme": "Problem Solution",
                "cta": "Book a quick consult",
                "notes": "Push the strongest early angle organically.",
            },
            {
                "period": "Week 3",
                "channel": "WhatsApp",
                "deliverable": "Follow-up message sequence",
                "theme": "Trust Builder",
                "cta": "See how it works",
                "notes": "Retarget engaged prospects with proof-led copy.",
            },
        ],
        "sections": [
            {
                "heading": "Implementation Notes",
                "body": "Start with angle testing, then scale the best performer into always-on creative.",
            }
        ],
    }


def _call_llm_for_plan(
    *,
    brief: str,
    title: str,
    client_context: str,
) -> dict[str, Any] | None:
    """Generate structured marketing-plan JSON from a plain brief."""
    prompt = (
        f"Create a marketing package from this brief:\n\n{brief}\n\n"
        f"Preferred title: {title}\n"
        f"{client_context}"
    )
    response = llm_chat(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2200,
        strip_preamble=True,
    )
    if not response:
        return None
    return _extract_json_object(response)


def run(
    *,
    brief: str,
    title: str = "",
    author: str = "Vizier",
    client_id: str = "",
    output_dir: str = "output/marketing-plan",
    package_mode: str = "document_bundle",
    generate_posters: bool = True,
    export_epub: bool = False,
    include_toc: bool = True,
    export_gamma: bool = False,
    gamma_format: str = "presentation",
    gamma_text_mode: str = "condense",
    gamma_export_as: str = "pdf",
    gamma_theme_id: str = "",
    gamma_folder_ids: list[str] | None = None,
    gamma_num_cards: int | None = None,
    gamma_card_split: str = "",
    gamma_card_dimensions: str = "",
    gamma_image_source: str = "noImages",
    gamma_image_model: str = "",
    gamma_image_style: str = "",
    gamma_image_style_preset: str = "",
    gamma_text_amount: str = "",
    gamma_tone: str = "professional",
    gamma_audience: str = "decision-makers",
    gamma_language: str = "",
    gamma_additional_instructions: str = "",
    gamma_template_id: str = "",
    gamma_template_prompt: str = "",
    gamma_header_footer: dict[str, object] | None = None,
    gamma_card_options: dict[str, object] | None = None,
    gamma_sharing_options: dict[str, object] | None = None,
    gamma_output_path: str = "",
) -> dict[str, Any]:
    """Generate a marketing plan package from a plain-language brief."""
    normalized_brief = brief.strip()
    if not normalized_brief:
        msg = "brief is required"
        raise ValueError(msg)

    client = load_client(client_id) if client_id else None
    effective_title = title.strip() or _derive_title(
        normalized_brief,
        client_name=client.client_name if client is not None else "",
    )
    client_context = ""
    brand = None
    poster_defaults: dict[str, object] | None = None
    if client is not None:
        brand = asdict(client.brand)
        poster_defaults = {"client_id": client.client_id}
        client_context = (
            f"Client name: {client.client_name}\n"
            f"Preferred language: {client.defaults.language}\n"
            f"Tone: {client.defaults.tone}\n"
            f"Style hint: {client.defaults.style_hint}\n"
            f"Style reference: {client.defaults.style_reference}\n"
        )

    payload = _call_llm_for_plan(
        brief=normalized_brief,
        title=effective_title,
        client_context=client_context,
    )
    source = "llm"
    if payload is None:
        payload = _fallback_plan(
            brief=normalized_brief,
            title=effective_title,
        )
        source = "fallback"

    effective_output_dir = (
        Path(output_dir)
        / slugify(str(payload.get("title", effective_title) or effective_title))
    )
    result = run_structured_nonfiction(
        title=str(payload.get("title", effective_title)),
        subtitle=str(payload.get("subtitle", "Strategy plan and creative pack")),
        author=author,
        output_dir=str(effective_output_dir),
        profile="marketing_plan",
        package_mode=package_mode,
        include_toc=include_toc,
        strategy=payload.get("strategy"),
        campaign_angles=payload.get("campaign_angles"),
        creative_variants=payload.get("creative_variants"),
        content_calendar=payload.get("content_calendar"),
        sections=payload.get("sections"),
        charts=payload.get("charts"),
        generate_posters=generate_posters,
        poster_defaults=poster_defaults,
        export_operational_assets=True,
        export_pdf=True,
        export_epub=export_epub,
        brand=brand,
        export_gamma=export_gamma,
        gamma_format=gamma_format,
        gamma_text_mode=gamma_text_mode,
        gamma_export_as=gamma_export_as,
        gamma_theme_id=gamma_theme_id,
        gamma_folder_ids=gamma_folder_ids,
        gamma_num_cards=gamma_num_cards,
        gamma_card_split=gamma_card_split,
        gamma_card_dimensions=gamma_card_dimensions,
        gamma_image_source=gamma_image_source,
        gamma_image_model=gamma_image_model,
        gamma_image_style=gamma_image_style,
        gamma_image_style_preset=gamma_image_style_preset,
        gamma_text_amount=gamma_text_amount,
        gamma_tone=gamma_tone,
        gamma_audience=gamma_audience,
        gamma_language=gamma_language,
        gamma_additional_instructions=gamma_additional_instructions,
        gamma_template_id=gamma_template_id,
        gamma_template_prompt=gamma_template_prompt,
        gamma_header_footer=gamma_header_footer,
        gamma_card_options=gamma_card_options,
        gamma_sharing_options=gamma_sharing_options,
        gamma_output_path=gamma_output_path,
    )
    result.update(
        {
            "brief": normalized_brief,
            "source": source,
            "pipeline": "marketing_plan_generate",
        }
    )
    if client is not None:
        result["client_id"] = client.client_id

    logger.info(
        "marketing_plan_generated",
        title=result["title"],
        source=source,
        client_id=client_id or None,
        output_dir=str(effective_output_dir),
    )
    return result
