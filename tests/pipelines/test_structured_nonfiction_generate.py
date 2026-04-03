"""Tests for structured_nonfiction_generate pipeline."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import patch
from types import SimpleNamespace

from unittest.mock import MagicMock

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)

from pipelines.nonfiction_ebook_generate import run as run_nonfiction_alias
from pipelines.structured_nonfiction_generate import run


def _write_fake_pdf(path: str) -> None:
    Path(path).write_bytes(b"%PDF-1.4")


def _write_fake_epub(path: str) -> None:
    Path(path).write_bytes(b"epub")


def _fake_chart_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    Path(output_path).write_bytes(b"png")
    return {"file_path": output_path}


def _fake_pdf_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    _write_fake_pdf(output_path)
    return {"file_path": output_path}


def _fake_epub_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    _write_fake_epub(output_path)
    return {"file_path": output_path}


def _fake_poster_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    Path(output_path).write_bytes(b"png")
    return {"poster_path": output_path}


def _fake_gamma_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    Path(output_path).write_bytes(b"%PDF-1.4")
    return {
        "generation_id": "gamma_123",
        "status": "completed",
        "gamma_url": "https://gamma.app/docs/gamma_123",
        "export_url": "https://gamma.app/export/gamma_123.pdf",
        "file_path": output_path,
    }


class TestStructuredNonfictionGenerate:
    def test_generates_single_document_exports_and_toc(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.structured_nonfiction_generate.chart_run",
                side_effect=_fake_chart_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run(
                title="SME Growth Playbook",
                author="Vizier",
                profile="marketing_plan",
                sections=[
                    {"heading": "Overview", "body": "Growth summary", "callout": "Key takeaways"},
                    {"heading": "Angles", "body": "Creative direction"},
                    {"heading": "Recommendations", "body": "Action plan"},
                ],
                charts=[
                    {
                        "section_heading": "Angles",
                        "chart_type": "bar",
                        "data": {"labels": ["A", "B"], "values": [10, 20]},
                        "title": "Angle Scores",
                    }
                ],
                output_dir=str(tmp_path / "book"),
            )

        assert result["status"] == "completed"
        assert result["profile"] == "marketing_plan"
        assert result["package_mode"] == "single_document"
        assert result["document_count"] == 1
        assert result["section_count"] == 3
        assert result["chart_count"] == 1
        assert Path(result["html_path"]).exists()
        assert Path(result["markdown_path"]).exists()
        assert Path(result["pdf_path"]).exists()
        assert Path(result["epub_path"]).exists()
        assert result["reference_trace"]["task_family"] == "document"
        assert set(result["reference_trace"]["lookup_tools_used"]) == {
            "search_report_layouts",
            "search_quarto_layouts",
        }
        assert result["quality_feedback"]["summary"]
        assert result["quality_feedback"]["improvement_priorities"]
        assert result["documents"][0]["quality_feedback"]["revision_hints"]
        html = Path(result["html_path"]).read_text(encoding="utf-8")
        assert "Table of Contents" in html
        assert ".pull-quote" in html
        assert result["quality_report"]["passed"] is True

    def test_generates_document_bundle(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.structured_nonfiction_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run(
                title="Campaign Dossier",
                author="Vizier",
                profile="campaign_dossier",
                package_mode="document_bundle",
                documents=[
                    {
                        "title": "Strategy Plan",
                        "slug": "strategy-plan",
                        "sections": [
                            {"heading": "Audience", "body": "Audience notes"},
                            {"heading": "Positioning", "body": "Positioning notes"},
                            {"heading": "Channels", "body": "Channel mix"},
                        ],
                    },
                    {
                        "title": "Creative Pack",
                        "slug": "creative-pack",
                        "sections": [
                            {"heading": "Angle One", "body": "Hero angle"},
                            {"heading": "Angle Two", "body": "Offer angle"},
                            {"heading": "Angle Three", "body": "Urgency angle"},
                        ],
                    },
                ],
                output_dir=str(tmp_path / "bundle"),
            )

        assert result["package_mode"] == "document_bundle"
        assert result["document_count"] == 2
        assert len(result["documents"]) == 2
        assert result["quality_feedback"]["document_feedback"]
        assert result["reference_trace"]["task_family"] == "document"
        assert result["documents"][0]["slug"] == "strategy-plan"
        assert Path(result["documents"][0]["html_path"]).exists()
        assert Path(result["documents"][1]["pdf_path"]).exists()

    def test_marketing_plan_bundle_auto_builds_strategy_and_creative_pack(
        self, tmp_path: Path
    ) -> None:
        with (
            patch(
                "pipelines.structured_nonfiction_generate.chart_run",
                side_effect=_fake_chart_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.poster_run",
                side_effect=_fake_poster_run,
            ) as poster_mock,
        ):
            result = run(
                title="Ramadan Cafe Growth Campaign",
                author="Vizier",
                profile="marketing_plan",
                package_mode="document_bundle",
                strategy={
                    "objective": "Acquire 500 qualified leads in four weeks.",
                    "audience": "Independent cafe owners preparing Ramadan offers.",
                    "offer": "A free campaign kit with posters, captions, and launch checklist.",
                    "positioning": "A practical growth system for lean cafe teams.",
                    "key_message": "Launch faster without looking generic.",
                    "channels": ["Meta Ads", "WhatsApp"],
                    "kpis": ["Cost per lead below RM8", "Landing page CVR above 12%"],
                    "timeline": "Four-week sprint leading into Ramadan.",
                    "primary_cta": "Download the campaign kit",
                    "recommended_actions": [
                        "Launch angle testing in week one",
                        "Retarget engaged viewers in week two",
                    ],
                },
                campaign_angles=[
                    {
                        "name": "Operations Relief",
                        "audience_segment": "Busy operators with tiny teams.",
                        "pain_point": "They do not have time to design fresh assets.",
                        "promise": "Ready-made campaigns remove the production bottleneck.",
                        "proof": "Includes templates, offers, and rollout checklist.",
                        "channels": ["Meta Ads"],
                        "visual_direction": "Warm cafe counter with action-oriented layout.",
                        "score": 9.1,
                    },
                    {
                        "name": "Festive Rush",
                        "audience_segment": "Owners expecting higher seasonal traffic.",
                        "pain_point": "Demand spikes arrive before creative is ready.",
                        "promise": "Seasonal offers can be launched before demand peaks.",
                        "proof": "Built from high-performing Ramadan promo structures.",
                        "channels": ["Instagram"],
                        "score": 8.4,
                    },
                ],
                creative_variants=[
                    {
                        "angle_name": "Operations Relief",
                        "channel": "Meta Ads",
                        "headline": "Busy Cafe? Launch Faster",
                        "body": "Use ready-made Ramadan creatives to fill your calendar this week.",
                        "cta": "Download the campaign kit",
                        "image_prompt": "Cafe owner reviewing branded Ramadan posters.",
                    },
                    {
                        "angle_name": "Festive Rush",
                        "channel": "Instagram",
                        "headline": "Ramadan Rush Starts Now",
                        "body": "Turn seasonal traffic into repeat buyers with sharper offers.",
                        "cta": "Get the launch pack",
                    },
                ],
                content_calendar=[
                    {
                        "period": "Week 1",
                        "channel": "Meta Ads",
                        "deliverable": "Angle test campaign",
                        "theme": "Operational relief",
                        "cta": "Download the kit",
                    },
                    {
                        "period": "Week 2",
                        "channel": "WhatsApp",
                        "deliverable": "Follow-up broadcast",
                        "theme": "Festive rush reminder",
                        "cta": "Book the setup call",
                    },
                ],
                sections=[
                    {
                        "heading": "Risk Register",
                        "body": "Refresh the winning angle weekly to prevent fatigue.",
                    }
                ],
                output_dir=str(tmp_path / "marketing"),
                generate_posters=True,
            )

        assert poster_mock.call_count == 2
        assert result["profile"] == "marketing_plan"
        assert result["package_mode"] == "document_bundle"
        assert result["document_count"] == 2
        assert result["campaign_angle_count"] == 2
        assert result["creative_variant_count"] == 2
        assert result["poster_count"] == 2
        assert len(result["poster_paths"]) == 2
        assert result["documents"][0]["title"].endswith("Strategy Plan")
        assert result["documents"][1]["title"].endswith("Creative Pack")
        assert result["documents"][0]["chart_count"] == 1
        assert result["operational_bundle_dir"].endswith("operational-assets")
        assert result["client_bundle_dir"].endswith("operational-assets/client")
        assert result["internal_bundle_dir"].endswith("operational-assets/internal")
        strategy_html = Path(result["documents"][0]["html_path"]).read_text(encoding="utf-8")
        creative_html = Path(result["documents"][1]["html_path"]).read_text(encoding="utf-8")
        manifest = json.loads(
            Path(result["operational_assets"]["manifest_path"]).read_text(
                encoding="utf-8"
            )
        )
        captions_csv = Path(
            result["operational_assets"]["captions_csv_path"]
        ).read_text(encoding="utf-8")
        first_client_asset = Path(
            result["operational_assets"]["assets"][0]["client_asset_dir"]
        )
        first_internal_asset = Path(
            result["operational_assets"]["assets"][0]["internal_asset_dir"]
        )
        assert "Campaign Angles" in strategy_html
        assert "Risk Register" in strategy_html
        assert "Creative Direction" in creative_html
        assert "Busy Cafe? Launch Faster" in creative_html
        assert manifest["variant_count"] == 2
        assert manifest["poster_count"] == 2
        assert "Busy Cafe? Launch Faster" in captions_csv
        assert not (first_client_asset / "copy.json").exists()
        assert not (first_client_asset / "notes.md").exists()
        assert (first_internal_asset / "copy.json").exists()
        assert (first_internal_asset / "notes.md").exists()
        assert any(
            Path(asset["client_asset_dir"]).exists()
            for asset in result["operational_assets"]["assets"]
        )
        assert any(
            Path(asset["poster_path"]).exists()
            for asset in result["operational_assets"]["assets"]
        )
        assert result["quality_feedback"]["summary"]
        assert result["quality_feedback"]["document_feedback"]
        assert result["quality_report"]["passed"] is True

    def test_exports_gamma_artifact_when_requested(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.structured_nonfiction_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.gamma_generate_run",
                side_effect=_fake_gamma_run,
            ) as gamma_mock,
        ):
            result = run(
                title="Client Strategy Deck Source",
                author="Vizier",
                profile="proposal",
                sections=[
                    {"heading": "Executive Summary", "body": "Summary body"},
                    {"heading": "Recommendations", "body": "Recommendation body"},
                    {"heading": "Next Steps", "body": "Action body"},
                ],
                output_dir=str(tmp_path / "gamma"),
                export_gamma=True,
                gamma_export_as="pdf",
                gamma_num_cards=9,
                gamma_card_dimensions="16x9",
                gamma_theme_id="theme_brand",
                gamma_folder_ids=["folder_marketing"],
                gamma_additional_instructions="Emphasize the rollout plan.",
                gamma_template_id="gamma_template_123",
            )

        assert result["gamma_url"] == "https://gamma.app/docs/gamma_123"
        assert Path(result["gamma_file_path"]).exists()
        assert result["gamma_generation"]["generation_id"] == "gamma_123"
        gamma_kwargs = gamma_mock.call_args.kwargs
        assert gamma_kwargs["format"] == "presentation"
        assert gamma_kwargs["text_mode"] == "condense"
        assert gamma_kwargs["theme_id"] == "theme_brand"
        assert gamma_kwargs["folder_ids"] == ["folder_marketing"]
        assert gamma_kwargs["num_cards"] == 9
        assert gamma_kwargs["card_dimensions"] == "16x9"
        assert gamma_kwargs["template_gamma_id"] == "gamma_template_123"
        assert "rollout plan" in gamma_kwargs["additional_instructions"]
        assert result["quality_report"]["passed"] is True

    def test_rejects_unknown_profile(self, tmp_path: Path) -> None:
        try:
            run(
                title="SME Growth Playbook",
                author="Vizier",
                profile="mystery_profile",
                sections=[
                    {"heading": "Overview", "body": "Growth summary"},
                    {"heading": "Angles", "body": "Creative direction"},
                    {"heading": "Recommendations", "body": "Action plan"},
                ],
                output_dir=str(tmp_path / "book"),
                export_pdf=False,
                export_epub=False,
            )
        except ValueError as exc:
            assert "profile" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

    def test_rejects_marketing_inputs_for_non_marketing_profile(
        self, tmp_path: Path
    ) -> None:
        try:
            run(
                title="General Ebook",
                author="Vizier",
                profile="ebook",
                strategy={"objective": "Should not be accepted here."},
                output_dir=str(tmp_path / "ebook"),
                export_pdf=False,
                export_epub=False,
            )
        except ValueError as exc:
            assert "marketing profiles" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

    def test_nonfiction_alias_uses_ebook_profile(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.structured_nonfiction_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run_nonfiction_alias(
                title="SME Growth Playbook",
                author="Vizier",
                sections=[
                    {"heading": "Overview", "body": "Growth summary"},
                    {"heading": "Angles", "body": "Creative direction"},
                    {"heading": "Recommendations", "body": "Action plan"},
                ],
                output_dir=str(tmp_path / "alias"),
            )

        assert result["profile"] == "ebook"
        assert result["package_mode"] == "single_document"

    def test_report_html_uses_passed_brand_tokens(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.structured_nonfiction_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.structured_nonfiction_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run(
                title="Client Narrative",
                author="Vizier",
                profile="proposal",
                sections=[
                    {"heading": "Overview", "body": "A tighter opening section with more signal.", "callout": "Lead with the decision."},
                    {"heading": "Evidence", "body": "Supporting proof and context live here."},
                    {"heading": "Next Steps", "body": "Clear action items conclude the document."},
                ],
                brand={
                    "primary_color": "#123456",
                    "secondary_color": "#f6efe2",
                    "accent_color": "#c6782b",
                    "headline_font": "Merriweather, serif",
                    "body_font": "Inter, sans-serif",
                },
                output_dir=str(tmp_path / "brand"),
            )

        html = Path(result["html_path"]).read_text(encoding="utf-8")
        assert "--primary:      #123456;" in html
        assert "--secondary:    #f6efe2;" in html
        assert "--accent:       #c6782b;" in html
        assert "--font-heading: Merriweather, serif;" in html
        assert "--font-body:    Inter, sans-serif;" in html
