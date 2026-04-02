"""Poster brief normalization and creative-brief assembly."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from adapter.llm_client import chat as llm_chat

_CTA_FALLBACK = "Learn More"
_HEADLINE_MAX_WORDS = 8
_BODY_MAX_CHARS = 160
_IMAGE_PROMPT_MAX_CHARS = 260


@dataclass(frozen=True)
class PosterCreativeBrief:
    """Normalized creative brief used to guide poster generation."""

    raw_brief: str = ""
    campaign_angle: str = ""
    audience: str = ""
    visual_direction: str = ""
    hero_focus: str = ""
    headline: str = ""
    body: str = ""
    cta: str = _CTA_FALLBACK
    image_prompt: str = ""
    template_name: str = ""
    avoid: tuple[str, ...] = ()


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def _clip_text(text: str, limit: int) -> str:
    compact = _collapse_whitespace(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _clip_words(text: str, limit: int) -> str:
    compact = _collapse_whitespace(text)
    words = compact.split()
    if len(words) <= limit:
        return compact
    return " ".join(words[:limit])


def _extract_json_object(text: str) -> dict[str, object] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_avoid(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = re.split(r"\s*(?:,|;|\|)\s*", value)
        return tuple(part for part in (_collapse_whitespace(item) for item in parts) if part)
    if isinstance(value, list):
        return tuple(
            part
            for part in (_collapse_whitespace(str(item)) for item in value)
            if part
        )
    return ()


def _fallback_headline(brief: str) -> str:
    if not brief:
        return ""
    sentence = re.split(r"[.!?\n]", brief, maxsplit=1)[0]
    sentence = re.sub(
        r"^(?:please|create|design|make|build|need|want|i want|i need)\s+",
        "",
        sentence.strip(),
        flags=re.IGNORECASE,
    )
    return _clip_words(sentence, _HEADLINE_MAX_WORDS)


def _fallback_body(brief: str) -> str:
    if not brief:
        return ""
    compact = _collapse_whitespace(brief)
    compact = re.sub(
        r"^(?:please|create|design|make|build|need|want|i want|i need)\s+",
        "",
        compact,
        flags=re.IGNORECASE,
    )
    return _clip_text(compact, _BODY_MAX_CHARS)


def _fallback_image_prompt(brief: str) -> str:
    if not brief:
        return ""
    return _clip_text(
        (
            f"{_collapse_whitespace(brief)}. Premium marketing poster background, "
            "hero-forward composition, no text, no logos, controlled lighting."
        ),
        _IMAGE_PROMPT_MAX_CHARS,
    )


def _build_fallback_brief(
    *,
    brief: str,
    headline: str,
    body: str,
    cta: str,
    image_prompt: str,
) -> PosterCreativeBrief:
    return PosterCreativeBrief(
        raw_brief=_collapse_whitespace(brief),
        headline=_clip_words(_collapse_whitespace(headline) or _fallback_headline(brief), _HEADLINE_MAX_WORDS),
        body=_clip_text(_collapse_whitespace(body) or _fallback_body(brief), _BODY_MAX_CHARS),
        cta=_clip_words(_collapse_whitespace(cta) or _CTA_FALLBACK, 3),
        image_prompt=_clip_text(
            _collapse_whitespace(image_prompt) or _fallback_image_prompt(brief),
            _IMAGE_PROMPT_MAX_CHARS,
        ),
    )


def _coalesce_text(primary: str, secondary: str, *, words: int | None = None, chars: int | None = None) -> str:
    value = _collapse_whitespace(primary) or _collapse_whitespace(secondary)
    if words is not None:
        value = _clip_words(value, words)
    if chars is not None:
        value = _clip_text(value, chars)
    return value


def normalize_poster_brief(
    *,
    brief: str = "",
    headline: str = "",
    body: str = "",
    cta: str = "",
    image_prompt: str = "",
    brand_name: str = "",
    style_hint: str = "",
    ambient_guidance: str = "",
    available_templates: list[str] | None = None,
) -> PosterCreativeBrief:
    """Normalize a raw poster brief into a reusable creative brief.

    Structured headline/body callers still work without invoking the model.
    When a freeform ``brief`` is present, this function converts it into
    cleaner poster-ready copy and art-direction hints.
    """
    available_templates = available_templates or []
    compact_brief = _collapse_whitespace(brief)
    if not compact_brief:
        return _build_fallback_brief(
            brief="",
            headline=headline,
            body=body,
            cta=cta,
            image_prompt=image_prompt,
        )

    prompt = {
        "raw_brief": compact_brief,
        "explicit_fields": {
            "headline": _collapse_whitespace(headline),
            "body": _collapse_whitespace(body),
            "cta": _collapse_whitespace(cta),
            "image_prompt": _collapse_whitespace(image_prompt),
            "brand_name": _collapse_whitespace(brand_name),
        },
        "style_hint": _collapse_whitespace(style_hint),
        "ambient_guidance": _collapse_whitespace(ambient_guidance),
        "available_templates": available_templates,
    }

    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You normalize freeform poster briefs into compact creative briefs "
                    "for a premium poster generator. Return ONLY valid JSON with keys "
                    '{"campaign_angle":"","audience":"","visual_direction":"","hero_focus":"",'
                    '"headline":"","body":"","cta":"","image_prompt":"","template_name":"","avoid":[]}. '
                    "Rules: preserve explicit user-supplied headline/body/cta/image_prompt when they "
                    "are already provided; otherwise generate sharper campaign-ready poster copy. "
                    "headline should usually be 3-8 words. body should be one or two short sentences, "
                    "well under 160 characters. cta should be 1-3 words. image_prompt must describe "
                    "the visual scene only, never include text or logos. template_name must be one of "
                    "the provided template names or an empty string. Avoid generic filler like "
                    "'Introducing' unless the brief truly needs it."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        max_tokens=450,
        timeout=45.0,
        strip_preamble=True,
    )

    payload = _extract_json_object(result or "")
    if payload is None:
        return _build_fallback_brief(
            brief=compact_brief,
            headline=headline,
            body=body,
            cta=cta,
            image_prompt=image_prompt,
        )

    template_name = _collapse_whitespace(str(payload.get("template_name", "")))
    if template_name and template_name not in available_templates:
        template_name = ""

    fallback = _build_fallback_brief(
        brief=compact_brief,
        headline=headline,
        body=body,
        cta=cta,
        image_prompt=image_prompt,
    )

    return PosterCreativeBrief(
        raw_brief=compact_brief,
        campaign_angle=_clip_text(_collapse_whitespace(str(payload.get("campaign_angle", ""))), 140),
        audience=_clip_text(_collapse_whitespace(str(payload.get("audience", ""))), 120),
        visual_direction=_clip_text(_collapse_whitespace(str(payload.get("visual_direction", ""))), 180),
        hero_focus=_clip_text(_collapse_whitespace(str(payload.get("hero_focus", ""))), 120),
        headline=_coalesce_text(
            headline,
            str(payload.get("headline", "")) or fallback.headline,
            words=_HEADLINE_MAX_WORDS,
        ),
        body=_coalesce_text(
            body,
            str(payload.get("body", "")) or fallback.body,
            chars=_BODY_MAX_CHARS,
        ),
        cta=_coalesce_text(
            cta,
            str(payload.get("cta", "")) or fallback.cta,
            words=3,
        ) or _CTA_FALLBACK,
        image_prompt=_coalesce_text(
            image_prompt,
            str(payload.get("image_prompt", "")) or fallback.image_prompt,
            chars=_IMAGE_PROMPT_MAX_CHARS,
        ),
        template_name=template_name,
        avoid=_normalize_avoid(payload.get("avoid")),
    )


def as_payload(creative_brief: PosterCreativeBrief) -> dict[str, Any]:
    """Convert a creative brief to a serializable dict."""
    return asdict(creative_brief)
