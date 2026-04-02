"""Tests for marketing_plan_generate pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipelines.marketing_plan_generate import run


class TestMarketingPlanGenerate:
    def test_calls_structured_nonfiction_with_llm_payload(self, tmp_path: Path) -> None:
        llm_payload = """
        {
          "title": "Cafe Launch Plan",
          "subtitle": "Strategy and creative pack",
          "strategy": {
            "objective": "Grow weekend footfall",
            "audience": "Young professionals",
            "offer": "Buy 1 free 1 drinks",
            "positioning": "Premium convenience",
            "key_message": "Fast treats for busy days",
            "channels": ["Meta Ads"],
            "kpis": ["Leads"],
            "recommended_actions": ["Launch angle testing"]
          },
          "campaign_angles": [
            {
              "name": "Speed",
              "promise": "Fast pickup",
              "proof": "Ready in 10 minutes",
              "channels": ["Meta Ads"],
              "score": 8.5
            }
          ],
          "creative_variants": [
            {
              "angle_name": "Speed",
              "channel": "Meta Ads",
              "headline": "Skip The Queue",
              "body": "Order ahead and collect fast",
              "cta": "Order now"
            }
          ],
          "content_calendar": [
            {
              "period": "Week 1",
              "channel": "Meta Ads",
              "deliverable": "Launch ads",
              "theme": "Speed",
              "cta": "Order now"
            }
          ],
          "sections": [
            {
              "heading": "Risk Register",
              "body": "Refresh creative every week."
            }
          ]
        }
        """
        fake_result = {"status": "completed", "title": "Cafe Launch Plan"}

        with (
            patch("pipelines.marketing_plan_generate.llm_chat", return_value=llm_payload),
            patch(
                "pipelines.marketing_plan_generate.run_structured_nonfiction",
                return_value=fake_result,
            ) as mock_structured,
        ):
            result = run(
                brief="Build a launch campaign for a new cafe.",
                client_id="dmb",
                output_dir=str(tmp_path),
            )

        assert result["status"] == "completed"
        assert result["source"] == "llm"
        assert result["client_id"] == "dmb"
        kwargs = mock_structured.call_args.kwargs
        assert kwargs["profile"] == "marketing_plan"
        assert kwargs["package_mode"] == "document_bundle"
        assert kwargs["generate_posters"] is True
        assert kwargs["poster_defaults"] == {"client_id": "dmb"}
        assert kwargs["brand"]["primary_color"] == "#2C1810"
        assert Path(kwargs["output_dir"]).parent == tmp_path

    def test_falls_back_when_llm_unavailable(self, tmp_path: Path) -> None:
        with patch("pipelines.marketing_plan_generate.llm_chat", return_value=None), patch(
            "pipelines.marketing_plan_generate.run_structured_nonfiction",
            return_value={"status": "completed", "title": "Fallback Title"},
        ) as mock_structured:
            result = run(
                brief="Need a marketing plan for premium kuih raya hampers.",
                output_dir=str(tmp_path),
            )

        assert result["source"] == "fallback"
        kwargs = mock_structured.call_args.kwargs
        assert kwargs["strategy"]["objective"] == "Need a marketing plan for premium kuih raya hampers."
        assert len(kwargs["campaign_angles"]) == 3
        assert kwargs["export_operational_assets"] is True
