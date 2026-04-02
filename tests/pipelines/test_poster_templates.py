"""Template-specific tests for ported visual inventory."""
from __future__ import annotations

from pathlib import Path

from pipelines.poster_generate import _inject_brand_css, _inject_slots, list_templates


ROOT = Path(__file__).resolve().parents[2]


class TestPosterTemplateInventory:
    def test_list_templates_returns_30_templates(self) -> None:
        assert len(list_templates()) == 30

    def test_all_templates_have_valid_reactor_meta(self) -> None:
        for template in list_templates():
            assert template.width > 0
            assert template.height > 0
            assert len(template.slots) >= 4

    def test_inject_slots_fills_brand_name_and_logo_mark(self) -> None:
        html = (ROOT / "templates" / "visual" / "bold-knockout-square.html").read_text(
            encoding="utf-8"
        )
        result = _inject_slots(
            html,
            {
                "headline": "Batik Baru",
                "body": "Tekstil premium",
                "cta": "Beli",
                "image_url": "data:image/png;base64,abc",
                "brand_name": "Desa Murni Batik",
                "logo_mark": "DMB",
            },
        )

        assert "Desa Murni Batik" in result
        assert "DMB" in result
        assert "{{brand_name}}" not in result
        assert "{{logo_mark}}" not in result

    def test_inject_brand_css_appends_root_overrides(self) -> None:
        html = "<html><head></head><body></body></html>"
        result = _inject_brand_css(html, {"--bg-color": "#111111", "--accent-color": "#c4956a"})
        assert "--bg-color: #111111;" in result
        assert "--accent-color: #c4956a;" in result

    def test_base_slot_templates_ignore_empty_brand_fields(self) -> None:
        for name in ("nike-overlay", "velos-split", "social-post"):
            html = (ROOT / "templates" / "visual" / f"{name}.html").read_text(
                encoding="utf-8"
            )
            result = _inject_slots(
                html,
                {
                    "headline": "Headline",
                    "body": "Body",
                    "cta": "CTA",
                    "image_url": "data:image/png;base64,abc",
                    "brand_name": "",
                    "logo_mark": "",
                },
            )
            assert "{{headline}}" not in result
            assert "{{body}}" not in result
            assert "{{cta}}" not in result
            assert "{{image_url}}" not in result
