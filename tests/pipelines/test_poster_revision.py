"""Tests for structured poster revision planning."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)

from pipelines.poster_revision import (
    build_revision_generate_kwargs,
    compile_revision_plan,
    run,
)


SAMPLE_STATE = {
    "latest_generated_poster_path": "/tmp/original-poster.png",
    "latest_reference_image_path": "/tmp/sample-reference.png",
    "latest_brief": "PETRONAS Raya premium festive poster",
    "latest_poster_args": {
        "brief": "PETRONAS Raya premium festive poster",
        "headline": "Selamat Hari Raya",
        "body": "Celebrate the season together.",
        "cta": "Learn more",
        "template_name": "social-post",
        "image_mode": "falai",
        "logo_mark": "PETRONAS",
        "palette": {
            "primary": "#00A19A",
            "secondary": "#E7F8F5",
            "accent": "#006A5B",
            "background": "#032B24",
            "text": "#F7FFF9",
        },
        "fonts": {
            "heading_font": "Cormorant Garamond",
            "heading_weight": "700",
            "body_font": "Lato",
            "body_weight": "400",
            "letter_spacing_heading": "-0.5px",
            "letter_spacing_body": "0px",
            "line_height_heading": "1.1",
            "line_height_body": "1.6",
        },
    },
    "latest_poster_result": {
        "poster_path": "/tmp/original-poster.png",
        "template_used": "social-post",
        "image_mode": "falai",
        "creative_brief": {
            "raw_brief": "PETRONAS Raya premium festive poster",
            "campaign_angle": "Premium festive greeting",
            "visual_direction": "Festive premium brand poster",
            "headline": "Selamat Hari Raya",
            "body": "Celebrate the season together.",
            "cta": "Learn more",
            "image_prompt": "Festive premium background, no text",
        },
    },
}


def test_compile_revision_plan_extracts_structured_change_goals() -> None:
    """Feedback becomes explicit revision goals instead of a loose regenerate."""
    plan = compile_revision_plan(
        feedback=(
            "Make the PETRONAS mark more visible, keep the premium festive feel, "
            "remove the duplicate greeting, clean up the layout, and improve mobile readability."
        ),
        latest_poster_state=SAMPLE_STATE,
    )

    keys = [goal.key for goal in plan.change_goals]
    assert "brand_visibility" in keys
    assert "single_main_headline" in keys
    assert "cleaner_hierarchy" in keys
    assert "mobile_readability" in keys
    assert "festive mood" in plan.preserve_strengths
    assert "premium feel" in plan.preserve_strengths
    assert "revising" in plan.telegram_intro.lower()


def test_build_revision_generate_kwargs_preserves_prior_state() -> None:
    """Revision generation should reuse prior poster inputs and active reference state."""
    plan = compile_revision_plan(
        feedback="Make the logo bigger and clean up the layout.",
        latest_poster_state=SAMPLE_STATE,
    )

    kwargs = build_revision_generate_kwargs(
        feedback="Make the logo bigger and clean up the layout.",
        latest_poster_state=SAMPLE_STATE,
        plan=plan,
    )

    assert kwargs["headline"] == "Selamat Hari Raya"
    assert kwargs["body"] == "Celebrate the season together."
    assert kwargs["template_name"] == "social-post"
    assert kwargs["image_mode"] == "falai"
    assert kwargs["reference_image_path"] == "/tmp/sample-reference.png"
    assert kwargs["palette"] == SAMPLE_STATE["latest_poster_args"]["palette"]
    assert kwargs["fonts"] == SAMPLE_STATE["latest_poster_args"]["fonts"]
    assert kwargs["output_path"].endswith("original-poster-revision.png")
    assert "Revise the existing poster instead of starting from scratch." in kwargs["brief"]
    assert "Increase the logo or brand mark prominence" in kwargs["brief"]


@patch("pipelines.poster_revision.generate_poster")
def test_run_returns_revision_plan_and_self_check(
    mock_generate_poster: MagicMock,
) -> None:
    """Revision execution returns the revised poster plus structured plan/check metadata."""
    mock_generate_poster.return_value = {
        "poster_path": "/tmp/revised-poster.png",
        "trace_path": "/tmp/revised-poster.trace.json",
        "creative_brief": {"headline": "Selamat Hari Raya"},
    }

    payload = run(
        feedback="Make the logo bigger and remove the duplicate headline.",
        latest_poster_state=SAMPLE_STATE,
    )

    assert payload["poster_path"] == "/tmp/revised-poster.png"
    assert payload["claim_level"] == "soft"
    assert payload["revision_plan"]["change_goals"][0]["key"] in {
        "brand_visibility",
        "single_main_headline",
    }
    assert payload["self_check"]
    assert payload["telegram_summary"]
    assert mock_generate_poster.called


def test_run_requires_prior_poster_state() -> None:
    """Revision should fail cleanly when no prior poster state exists."""
    with pytest.raises(ValueError, match="No prior poster state"):
        run(
            feedback="Make it cleaner.",
            latest_poster_state={},
        )
