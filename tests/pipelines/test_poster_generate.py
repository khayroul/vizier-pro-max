"""Tests for poster_generate pipeline — two-layer AI background + Playwright."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipelines.poster_generate import (
    PosterRequest,
    PosterResult,
    TemplateConfig,
    _build_design_css,
    _build_font_link,
    _inject_brand_css,
    _inject_design,
    _inject_slots,
    _parse_template,
    _resolve_template,
    _to_data_uri,
    _validate_palette,
    list_templates,
    run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PALETTE = {
    "primary": "#E07A5F",
    "secondary": "#F2CC8F",
    "accent": "#81B29A",
    "background": "#3D405B",
    "text": "#F4F1DE",
}

SAMPLE_FONTS = {
    "heading_font": "Cormorant Garamond",
    "heading_weight": "700",
    "body_font": "Lato",
    "body_weight": "400",
    "letter_spacing_heading": "-0.5px",
    "letter_spacing_body": "0px",
    "line_height_heading": "1.1",
    "line_height_body": "1.6",
}


# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------


class TestParseTemplate:
    def test_parses_meta_tags(self, tmp_path: Path) -> None:
        """Extracts width, height, and slots from reactor meta tags."""
        html = (
            '<meta name="reactor-width" content="1080">'
            '<meta name="reactor-height" content="1920">'
            '<meta name="reactor-slots" content="headline,body,cta">'
        )
        html_file = tmp_path / "test.html"
        html_file.write_text(html)

        config = _parse_template(html_file)

        assert config.name == "test"
        assert config.width == 1080
        assert config.height == 1920
        assert config.slots == ["headline", "body", "cta"]

    def test_defaults_when_no_meta(self, tmp_path: Path) -> None:
        """Falls back to 1080x1080 when no meta tags present."""
        html_file = tmp_path / "plain.html"
        html_file.write_text("<html><body>plain</body></html>")

        config = _parse_template(html_file)

        assert config.width == 1080
        assert config.height == 1080
        assert config.slots == []


class TestResolveTemplate:
    def test_resolves_existing_template(self) -> None:
        """social-post template resolves from templates/visual/."""
        config = _resolve_template("social-post")
        assert config.name == "social-post"
        assert config.width == 1080
        assert config.height == 1080
        assert "headline" in config.slots

    def test_missing_template_raises(self) -> None:
        """Unknown template raises FileNotFoundError with available list."""
        with pytest.raises(FileNotFoundError, match="not found"):
            _resolve_template("nonexistent-template")


class TestListTemplates:
    def test_lists_available_templates(self) -> None:
        """list_templates returns the full visual inventory including social-post."""
        templates = list_templates()
        names = [t.name for t in templates]
        assert "social-post" in names
        assert len(templates) >= 30


# ---------------------------------------------------------------------------
# Slot injection
# ---------------------------------------------------------------------------


class TestInjectSlots:
    def test_replaces_slots(self) -> None:
        html = "<h1>{{headline}}</h1><p>{{body}}</p>"
        result = _inject_slots(html, {"headline": "Hello", "body": "World"})
        assert result == "<h1>Hello</h1><p>World</p>"

    def test_missing_slot_becomes_empty(self) -> None:
        html = "<h1>{{headline}}</h1><p>{{missing}}</p>"
        result = _inject_slots(html, {"headline": "Hi"})
        assert result == "<h1>Hi</h1><p></p>"

    def test_no_slots_unchanged(self) -> None:
        html = "<p>no slots here</p>"
        result = _inject_slots(html, {"headline": "ignored"})
        assert result == html


# ---------------------------------------------------------------------------
# Data URI encoding
# ---------------------------------------------------------------------------


class TestToDataUri:
    def test_png_data_uri(self, tmp_path: Path) -> None:
        """PNG file encodes to data:image/png;base64,..."""
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        uri = _to_data_uri(img)

        assert uri.startswith("data:image/png;base64,")
        assert len(uri) > 30

    def test_jpg_data_uri(self, tmp_path: Path) -> None:
        """JPEG file uses image/jpeg mime type."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        uri = _to_data_uri(img)

        assert uri.startswith("data:image/jpeg;base64,")


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_poster_request_frozen(self) -> None:
        req = PosterRequest(headline="Test", body="Body")
        with pytest.raises(AttributeError):
            req.headline = "Modified"  # type: ignore[misc]

    def test_poster_result_frozen(self) -> None:
        result = PosterResult(
            poster_path="/tmp/p.png",
            hero_path="/tmp/h.png",
            template_used="social-post",
            width=1080,
            height=1080,
            image_mode="openai",
        )
        with pytest.raises(AttributeError):
            result.poster_path = "/changed"  # type: ignore[misc]

    def test_poster_request_defaults(self) -> None:
        req = PosterRequest(headline="Test", body="Body")
        assert req.cta == "Learn More"
        assert req.template_name == ""
        assert req.image_mode == ""
        assert req.brand_name == ""
        assert req.logo_mark == ""
        assert req.brand_css is None
        assert req.client_id == ""
        assert req.style_reference == ""
        assert req.palette is None
        assert req.fonts is None


# ---------------------------------------------------------------------------
# Palette validation
# ---------------------------------------------------------------------------


class TestValidatePalette:
    def test_valid_palette_passes(self) -> None:
        _validate_palette(SAMPLE_PALETTE)

    def test_invalid_hex_raises(self) -> None:
        bad_palette = {**SAMPLE_PALETTE, "primary": "not-a-color"}
        with pytest.raises(ValueError, match="Invalid hex color for palette.primary"):
            _validate_palette(bad_palette)

    def test_missing_key_raises(self) -> None:
        incomplete = {"primary": "#FFF", "secondary": "#000"}
        with pytest.raises(ValueError, match="palette.accent"):
            _validate_palette(incomplete)

    @pytest.mark.parametrize(
        "hex_val",
        ["#FFF", "#FFFF", "#AABBCC", "#AABBCCDD"],
    )
    def test_accepts_valid_hex_lengths(self, hex_val: str) -> None:
        palette = {**SAMPLE_PALETTE, "primary": hex_val}
        _validate_palette(palette)

    @pytest.mark.parametrize(
        "hex_val",
        ["#12", "#12345", "#1234567", "#123456789", "FFF", ""],
    )
    def test_rejects_invalid_hex(self, hex_val: str) -> None:
        palette = {**SAMPLE_PALETTE, "primary": hex_val}
        with pytest.raises(ValueError):
            _validate_palette(palette)


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------


class TestBuildDesignCss:
    def test_contains_all_custom_properties(self) -> None:
        css = _build_design_css(SAMPLE_PALETTE, SAMPLE_FONTS)
        assert "--color-accent: #E07A5F" in css
        assert "--color-accent-end: #F2CC8F" in css
        assert "--color-accent-glow: #81B29A" in css
        assert "--color-bg: #3D405B" in css
        assert "--color-text: #F4F1DE" in css
        assert "--font-heading: 'Cormorant Garamond'" in css
        assert "--font-body: 'Lato'" in css
        assert "--font-weight-heading: 700" in css
        assert "--font-weight-body: 400" in css

    def test_wrapped_in_style_tag(self) -> None:
        css = _build_design_css(SAMPLE_PALETTE, SAMPLE_FONTS)
        assert css.startswith("<style>")
        assert css.endswith("</style>")

    def test_no_curly_brace_corruption(self) -> None:
        """CSS curly braces must not be treated as {{slot}} placeholders."""
        css = _build_design_css(SAMPLE_PALETTE, SAMPLE_FONTS)
        # Should not match the {{word}} slot pattern
        slot_matches = re.findall(r"\{\{(\w+)\}\}", css)
        assert slot_matches == []


class TestBuildFontLink:
    def test_includes_heading_font(self) -> None:
        link = _build_font_link(SAMPLE_FONTS)
        assert "Cormorant+Garamond" in link

    def test_includes_body_font(self) -> None:
        link = _build_font_link(SAMPLE_FONTS)
        assert "Lato" in link

    def test_includes_600_weight_for_cta(self) -> None:
        """Body font weights must include 600 for CTA button."""
        link = _build_font_link(SAMPLE_FONTS)
        # Body part should have both 400 and 600
        assert "400;600" in link

    def test_is_link_tag(self) -> None:
        link = _build_font_link(SAMPLE_FONTS)
        assert link.startswith('<link href="https://fonts.googleapis.com')
        assert 'rel="stylesheet">' in link

    def test_deduplicates_600_weight(self) -> None:
        """If body_weight is already 600, don't duplicate it."""
        fonts_600 = {**SAMPLE_FONTS, "body_weight": "600"}
        link = _build_font_link(fonts_600)
        # Should contain just "600", not "600;600"
        assert "600;600" not in link


class TestInjectDesign:
    def test_inserts_before_head_close(self) -> None:
        html = "<html><head><title>Test</title></head><body></body></html>"
        result = _inject_design(html, SAMPLE_PALETTE, SAMPLE_FONTS)
        assert "</style>\n<link" in result
        assert result.index("<style>") < result.index("</head>")

    def test_preserves_existing_content(self) -> None:
        html = "<html><head><title>Test</title></head><body>Hello</body></html>"
        result = _inject_design(html, SAMPLE_PALETTE, SAMPLE_FONTS)
        assert "<title>Test</title>" in result
        assert "Hello" in result

    def test_css_not_corrupted_by_slot_regex(self) -> None:
        """Injected CSS must survive _inject_slots without corruption."""
        html = "<html><head></head><body>{{headline}}</body></html>"
        designed = _inject_design(html, SAMPLE_PALETTE, SAMPLE_FONTS)
        slotted = re.sub(r"\{\{(\w+)\}\}", lambda m: "REPLACED", designed)
        # CSS custom properties should still be intact
        assert "--color-accent: #E07A5F" in slotted


class TestInjectBrandCss:
    def test_inserts_root_override(self) -> None:
        html = "<html><head></head><body>Poster</body></html>"
        result = _inject_brand_css(html, {"--bg-color": "#111111", "--accent-color": "#abcdef"})
        assert "--bg-color: #111111;" in result
        assert "--accent-color: #abcdef;" in result
        assert result.index("<style>") < result.index("</head>")


# ---------------------------------------------------------------------------
# Full pipeline (mocked AI + Playwright)
# ---------------------------------------------------------------------------


class TestRunPipeline:
    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_full_pipeline_with_palette_fonts(
        self, mock_hero: MagicMock, mock_screenshot: MagicMock, tmp_path: Path
    ) -> None:
        """Full pipeline with palette and fonts injects CSS custom properties."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Jazz Festival",
            body="Live music under the stars",
            cta="Get Tickets",
            image_prompt="jazz festival background",
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["template_used"] == "social-post"
        assert result["width"] == 1080

        # Verify screenshot was called with HTML containing CSS vars
        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "--color-accent: #E07A5F" in html_arg
        assert "Cormorant+Garamond" in html_arg
        assert "Jazz Festival" in html_arg

    def test_none_palette_raises(self) -> None:
        """run() raises ValueError when only fonts are provided."""
        with pytest.raises(ValueError, match="palette and fonts must be provided together"):
            run(
                headline="Test",
                body="Body",
                palette=None,
                fonts=SAMPLE_FONTS,
            )

    def test_none_fonts_raises(self) -> None:
        """run() raises ValueError when only palette is provided."""
        with pytest.raises(ValueError, match="palette and fonts must be provided together"):
            run(
                headline="Test",
                body="Body",
                palette=SAMPLE_PALETTE,
                fonts=None,
            )

    def test_missing_theme_inputs_raises(self) -> None:
        """run() raises ValueError when neither design nor client theming is provided."""
        with pytest.raises(ValueError, match="palette/fonts or brand_css/client_id are required"):
            run(
                headline="Test",
                body="Body",
            )

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_style_reference_applies_catalog_defaults(
        self, mock_hero: MagicMock, mock_screenshot: MagicMock, tmp_path: Path
    ) -> None:
        """style_reference can drive template, prompt, and theming without client_id."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert "modern Malaysian coffee branding" in prompt
            assert "Avoid overly corporate finance look" in prompt
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Iced Latte Drop",
            body="Special launch promo for coffee lovers",
            style_reference="zus-coffee",
            output_path=str(tmp_path / "poster.png"),
        )

        assert result["template_used"] == "center-stage-square"
        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "--bg-color: #0D2B4D;" in html_arg
        assert "--accent-color: #D38B3D;" in html_arg

    def test_unknown_style_reference_raises(self) -> None:
        """Unknown shared style references should fail clearly."""
        with pytest.raises(ValueError, match="Unknown style_reference"):
            run(
                headline="Test",
                body="Body",
                style_reference="unknown-style",
            )

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_auto_prompt_from_headline_body(
        self, mock_hero: MagicMock, mock_screenshot: MagicMock, tmp_path: Path
    ) -> None:
        """When no image_prompt, auto-generates from headline + body."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert "Premium Launch" in prompt
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Premium Launch",
            body="Our newest product is here",
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["template_used"] == "social-post"
        mock_hero.assert_called_once()

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_falai_mode(
        self, mock_hero: MagicMock, mock_screenshot: MagicMock, tmp_path: Path
    ) -> None:
        """image_mode='falai' is passed through correctly."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert mode == "falai"
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Test",
            body="Body text",
            image_mode="falai",
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["image_mode"] == "falai"

    def test_invalid_template_raises(self) -> None:
        """Unknown template_name raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            run(
                headline="Test",
                body="Body",
                template_name="nonexistent",
                palette=SAMPLE_PALETTE,
                fonts=SAMPLE_FONTS,
            )

    def test_invalid_mode_raises(self) -> None:
        """Invalid image_mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid image_mode"):
            run(
                headline="Test",
                body="Body",
                image_mode="dalle",
                palette=SAMPLE_PALETTE,
                fonts=SAMPLE_FONTS,
            )


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    def test_plugin_registers_tool(self) -> None:
        """plugins/poster_tool.py registers generate_poster via ctx."""
        from plugins.poster_tool import register

        ctx = MagicMock()
        register(ctx)

        ctx.register_tool.assert_called_once()
        call_kwargs = ctx.register_tool.call_args[1]
        assert call_kwargs["name"] == "generate_poster"
        assert call_kwargs["toolset"] == "vizier-visual"
        assert "headline" in call_kwargs["schema"]["properties"]
        assert "body" in call_kwargs["schema"]["properties"]
        assert "palette" in call_kwargs["schema"]["properties"]
        assert "fonts" in call_kwargs["schema"]["properties"]

        ctx.register_hook.assert_called_once()
        hook_args = ctx.register_hook.call_args[0]
        assert hook_args[0] == "on_agent_ready"
        assert callable(hook_args[1])

    def test_schema_supports_client_theming_fields(self) -> None:
        """Schema exposes client-aware poster theming fields."""
        from plugins.poster_tool import GENERATE_POSTER_SCHEMA

        assert GENERATE_POSTER_SCHEMA["required"] == ["headline", "body"]
        assert "client_id" in GENERATE_POSTER_SCHEMA["properties"]
        assert "style_reference" in GENERATE_POSTER_SCHEMA["properties"]
        assert "brand_name" in GENERATE_POSTER_SCHEMA["properties"]
        assert "logo_mark" in GENERATE_POSTER_SCHEMA["properties"]
        assert "brand_css" in GENERATE_POSTER_SCHEMA["properties"]
