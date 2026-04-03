"""Tests for poster brief normalization."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)

from pipelines.poster_brief import (
    PosterCreativeBrief,
    as_payload,
    compile_poster_revision_plan,
    normalize_poster_brief,
)


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
    assert brief.cta == "Learn More"
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


@patch("pipelines.poster_brief.llm_chat")
def test_generic_model_cta_is_sharpened_from_context(mock_llm: MagicMock) -> None:
    """Weak generic CTAs should become action-led when the scenario is obvious."""
    mock_llm.return_value = json.dumps(
        {
            "campaign_angle": "Urgent relief support",
            "audience": "Donors",
            "visual_direction": "Minimal trust-led donation poster",
            "hero_focus": "Calm relief scene",
            "headline": "Introducing Relief That Reaches Faster",
            "body": "Help families access food and shelter without delay.",
            "cta": "Learn More",
            "image_prompt": "Calm trust-led relief visual, no text, no logos",
            "template_name": "",
            "avoid": ["exploitative imagery"],
        }
    )

    brief = normalize_poster_brief(
        brief="Create a trustworthy disaster-relief fundraiser poster with a clear donation ask.",
        available_templates=["social-post", "hero-bottom-text-square"],
    )

    assert brief.headline == "Relief That Reaches Faster"
    assert brief.cta == "Donate Now"


def test_fallback_cta_infers_event_action_from_brief() -> None:
    """Fallback normalization should infer stronger event CTAs from the brief text."""
    brief = normalize_poster_brief(
        brief="Design a synthwave music festival poster with bold type and clear ticket action.",
        available_templates=["social-post"],
    )

    assert brief.cta == "Get Tickets"


def test_compile_revision_plan_extracts_structured_goals() -> None:
    plan = compile_poster_revision_plan(
        "I can't see the logo and there are two text of Selamat Hari Raya. Layout is not good.",
        prior_creative_brief=PosterCreativeBrief(
            raw_brief="Premium Raya campaign poster",
            visual_direction="Festive premium poster",
            hero_focus="crescent lantern hero",
        ),
        prior_template_name="social-post",
        brand_name="PETRONAS",
        logo_mark="P",
    )

    assert "bigger logo mark" in plan.summary
    assert "one main headline only" in plan.summary
    assert plan.requires_hero_refresh is True
    assert plan.requires_logo_emphasis is True
    assert plan.requires_layout_cleanup is True
    assert plan.preferred_template_name == "hero-bottom-text-square"
    assert any("festive mood" in item.lower() for item in plan.preserve_goals)
    assert any("premium feel" in item.lower() for item in plan.preserve_goals)


def test_compile_revision_plan_uses_reference_image_as_change_signal() -> None:
    plan = compile_poster_revision_plan(
        "Please revise this with a cleaner hierarchy.",
        prior_creative_brief=PosterCreativeBrief(
            visual_direction="Premium editorial launch creative",
            hero_focus="bottle hero",
        ),
        prior_template_name="social-post",
        reference_image_path="/tmp/reference.jpg",
    )

    assert plan.requires_hero_refresh is True
    assert any("reference image" in goal.lower() for goal in plan.change_goals)
