"""Tests for ambient local-reference orchestration helpers."""
from __future__ import annotations

from references.ambient import (
    build_ambient_turn_context,
    build_chart_reference_context,
    build_document_reference_context,
    build_visual_reference_context,
)


class TestAmbientReferences:
    def test_builds_visual_reference_context_from_local_corpora(self) -> None:
        context = build_visual_reference_context(
            headline="Swiss dashboard launch",
            body="Smooth onboarding and clear form validation for a SaaS homepage.",
            image_prompt="minimal swiss grid, product-led hero, smooth scroll navigation",
            brand_name="LaunchOS",
            brief="Create a premium visual landing hero with a strong CTA.",
        )

        assert context["task_family"] == "visual"
        assert context["auto_consulted"] is True
        assert set(context["lookup_tools_used"]) == {
            "search_ui_styles",
            "search_ux_guidelines",
        }
        assert set(context["dataset_searches_used"]) == {
            "search_landing_patterns",
            "search_typography_pairings",
            "search_color_systems",
        }
        assert context["material_influences"]
        assert context["art_direction"]["template_candidates"]
        assert context["guidance"]

    def test_visual_context_prefers_product_hero_templates_for_launch_posters(self) -> None:
        context = build_visual_reference_context(
            headline="The Cold Brew Drop",
            body="Limited release. Bright citrus notes, silky finish, and launch-day energy.",
            image_prompt="Premium iced coffee hero, polished lighting, no text, no logos",
            brief=(
                "Create a premium poster for a limited-edition iced coffee drop "
                "with a strong product hero, polished lighting, and social-ready hierarchy."
            ),
        )

        assert context["art_direction"]["composition_mode"] == "product_hero"
        assert context["art_direction"]["template_candidates"][0] == "center-stage-square"

    def test_visual_context_filters_irrelevant_ux_prompt_noise(self) -> None:
        context = build_visual_reference_context(
            headline="Finance Without Noise",
            body="Help CFOs scan runway, risk, and forecast health in seconds.",
            image_prompt="Crisp analytics surface, swiss grid, controlled light, no text, no logos",
            brief=(
                "Create a premium hero for a CFO analytics platform that helps finance "
                "teams see runway, forecast risk, and cash health without clutter."
            ),
        )

        assert "scroll-behavior" not in context["art_direction"]["readability"].lower()
        assert "placeholder as only label" not in context["art_direction"]["readability"].lower()

    def test_builds_chart_reference_context_per_chart(self) -> None:
        context = build_chart_reference_context(
            title="Executive KPI Report",
            charts=[
                {
                    "title": "Monthly Revenue Trend",
                    "chart_type": "line",
                    "section_heading": "Performance",
                }
            ],
        )

        assert context["task_family"] == "chart"
        assert context["query_count"] == 1
        assert context["searches"][0]["tool_name"] == "search_chart_patterns"
        assert any(
            "Line Chart" in search["guidance"] or "Trend Over Time" in search["guidance"]
            for search in context["searches"]
        )

    def test_builds_document_reference_context_for_longform_reports(self) -> None:
        context = build_document_reference_context(
            title="Quarterly Growth Report",
            subtitle="Investor update with tables and callouts",
            profile="report",
            package_mode="single_document",
            document_titles=["Executive Summary", "Performance Tables", "Recommendations"],
            section_headings=["Revenue Mix", "Callouts", "Appendix"],
        )

        assert context["task_family"] == "document"
        assert context["auto_consulted"] is True
        assert {
            search["tool_name"]
            for search in context["searches"]
        } == {"search_report_layouts", "search_quarto_layouts"}
        assert context["guidance"]

    def test_turn_context_exposes_capability_map_and_live_guidance(self) -> None:
        turn_context = build_ambient_turn_context(
            "Prepare a quarterly report with charts and a polished layout."
        )

        assert "search_chart_patterns" in turn_context
        assert "search_report_layouts + search_quarto_layouts" in turn_context
        assert "Hermes remains the only runtime" in turn_context
        assert "Automatic local reference guidance for this request" in turn_context
