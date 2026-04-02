"""Tests for poster brief normalization."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from pipelines.poster_brief import PosterCreativeBrief, as_payload, normalize_poster_brief


def test_structured_inputs_skip_model_call() -> None:
    """Existing structured headline/body callers should not invoke the model."""
    with patch("pipelines.poster_brief.llm_chat") as mock_llm:
        brief = normalize_poster_brief(
            headline="New year. New power.",
            body="Meet Mac mini with M4.",
            cta="Learn more",
            image_prompt="Premium studio background, no text",
        )

    assert isinstance(brief, PosterCreativeBrief)
    assert brief.headline == "New year. New power."
    assert brief.body == "Meet Mac mini with M4."
    assert brief.cta == "Learn more"
    assert brief.image_prompt == "Premium studio background, no text"
    mock_llm.assert_not_called()


@patch("pipelines.poster_brief.llm_chat")
def test_freeform_brief_normalizes_into_creative_fields(mock_llm: MagicMock) -> None:
    """Freeform briefs become a compact structured creative brief."""
    mock_llm.return_value = json.dumps(
        {
            "campaign_angle": "New Year performance upgrade",
            "audience": "Design-conscious Apple buyers",
            "visual_direction": "Minimal premium product poster with a large centered hero",
            "hero_focus": "Mac mini M4 in clean studio light",
            "headline": "New year. New power.",
            "body": "Meet Mac mini with M4.",
            "cta": "Learn more",
            "image_prompt": "Compact desktop hero, silver finish, premium lighting, no text",
            "template_name": "social-post",
            "avoid": ["dense copy", "busy confetti"],
        }
    )

    brief = normalize_poster_brief(
        brief="Create an Apple-style New Year poster to sell Mac mini M4.",
        available_templates=["social-post", "center-stage-square"],
    )

    assert brief.campaign_angle == "New Year performance upgrade"
    assert brief.audience == "Design-conscious Apple buyers"
    assert brief.visual_direction == "Minimal premium product poster with a large centered hero"
    assert brief.hero_focus == "Mac mini M4 in clean studio light"
    assert brief.headline == "New year. New power."
    assert brief.body == "Meet Mac mini with M4."
    assert brief.cta == "Learn more"
    assert brief.image_prompt == "Compact desktop hero, silver finish, premium lighting, no text"
    assert brief.template_name == "social-post"
    assert brief.avoid == ("dense copy", "busy confetti")


@patch("pipelines.poster_brief.llm_chat")
def test_invalid_model_payload_falls_back_to_safe_brief(mock_llm: MagicMock) -> None:
    """Invalid model output should still produce usable fallback copy."""
    mock_llm.return_value = "not valid json"

    brief = normalize_poster_brief(
        brief="Design a premium poster for the Mac mini M4 New Year campaign.",
        available_templates=["social-post"],
    )

    assert brief.headline
    assert brief.body
    assert brief.cta == "Learn More"
    assert "premium marketing poster background" in brief.image_prompt.lower()
    assert brief.template_name == ""


def test_as_payload_serializes_creative_brief() -> None:
    """Creative briefs can be attached to poster results as serializable payloads."""
    payload = as_payload(
        PosterCreativeBrief(
            raw_brief="raw",
            campaign_angle="angle",
            audience="audience",
            visual_direction="direction",
            hero_focus="hero",
            headline="Headline",
            body="Body",
            cta="Learn more",
            image_prompt="Prompt",
            template_name="social-post",
            avoid=("tiny copy", "muddy lighting"),
        )
    )

    assert payload["headline"] == "Headline"
    assert payload["template_name"] == "social-post"
    assert payload["avoid"] == ("tiny copy", "muddy lighting")
