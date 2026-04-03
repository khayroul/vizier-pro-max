"""Tests for poster_generate pipeline — two-layer AI background + Playwright."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)

from middleware.deliverable_context import clear_context, set_context
from pipelines.poster_generate import (
    PosterRequest,
    PosterResult,
    TemplateConfig,
    _build_subject_clarity_guardrail,
    _build_design_css,
    _build_font_link,
    _generate_hero_openai,
    _generate_hero_falai,
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


class _GatewayResponse:
    def __init__(
        self,
        status_code: int,
        body: dict[str, object],
        *,
        text: str | None = None,
        content: bytes | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body)
        self.content = content if content is not None else self.text.encode("utf-8")

    def json(self) -> dict[str, object]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


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
        assert req.cta == ""
        assert req.brief == ""
        assert req.template_name == ""
        assert req.image_mode == ""
        assert req.brand_name == ""
        assert req.logo_mark == ""
        assert req.logo_image_path == ""
        assert req.brand_css is None
        assert req.client_id == ""
        assert req.style_reference == ""
        assert req.reference_image_path == ""
        assert req.palette is None
        assert req.fonts is None
        assert req.revision_goals is None
        assert req.preserve_goals is None
        assert req.prior_poster_context is None


class TestSubjectClarityGuardrail:
    def test_product_prompts_forbid_abstract_placeholders(self) -> None:
        brief = SimpleNamespace(
            raw_brief="Create a premium poster for a limited-edition iced coffee drop.",
            campaign_angle="Limited drop with a premium cafe feel",
            visual_direction="Hero-forward premium product poster",
            hero_focus="Large iced coffee product hero with glossy highlights and negative space",
            image_prompt="Premium iced coffee hero, polished lighting, no text, no logos",
        )

        guardrail = _build_subject_clarity_guardrail(brief)

        assert "recognizable physical product hero" in guardrail
        assert "abstract geometric stand-ins" in guardrail


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
        assert "--bg-color: #3D405B" in css
        assert "--accent-color: #81B29A" in css
        assert "--text-color: #F4F1DE" in css
        assert "--text-muted: rgba(244, 241, 222, 0.72)" in css
        assert "--font-headline: 'Cormorant Garamond'" in css
        assert "--font-headline-weight: 700" in css
        assert "--font-body-weight: 400" in css
        assert "--color-accent: #81B29A" in css
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
        assert "--accent-color: #81B29A" in slotted
        assert "--color-accent: #81B29A" in slotted


class TestInjectBrandCss:
    def test_inserts_root_override(self) -> None:
        html = "<html><head></head><body>Poster</body></html>"
        result = _inject_brand_css(html, {"--bg-color": "#111111", "--accent-color": "#abcdef"})
        assert "--bg-color: #111111;" in result
        assert "--accent-color: #abcdef;" in result
        assert result.index("<style>") < result.index("</head>")


# ---------------------------------------------------------------------------
# Gateway-backed hero generation
# ---------------------------------------------------------------------------


class TestGenerateHeroOpenAi:
    def test_routes_image_generation_through_gateway(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        requests: list[dict[str, object]] = []
        output_path = tmp_path / "hero.png"

        def _fake_post(url: str, **kwargs: object) -> _GatewayResponse:
            requests.append({"url": url, **kwargs})
            return _GatewayResponse(
                200,
                {"data": [{"b64_json": base64.b64encode(b"gateway-image").decode("ascii")}]},
            )

        monkeypatch.setattr("pipelines.poster_generate.httpx.post", _fake_post)
        monkeypatch.setenv("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:11436/v1")

        set_context("deliverable-123", "client-abc")
        try:
            hero_path = _generate_hero_openai("coffee poster hero", str(output_path))
        finally:
            clear_context()

        assert hero_path == str(output_path)
        assert output_path.read_bytes() == b"gateway-image"
        assert len(requests) == 1
        assert requests[0]["url"] == "http://127.0.0.1:11436/v1/images/generations"
        assert requests[0]["json"] == {
            "model": "gpt-image-1",
            "prompt": "coffee poster hero",
            "size": "1024x1024",
            "quality": "medium",
            "n": 1,
        }
        headers = requests[0]["headers"]
        assert isinstance(headers, dict)
        assert headers["x-vizier-source"] == "pipeline"
        assert headers["x-vizier-modality"] == "image_generation"
        assert headers["x-vizier-deliverable-id"] == "deliverable-123"
        assert headers["x-vizier-client-id"] == "client-abc"
        assert headers["x-vizier-pipeline-name"] == "poster_generate"
        assert headers["x-vizier-pipeline-version"] == "1.0"
        assert headers["x-vizier-step-name"] == "hero_generate"

    def test_raises_when_gateway_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def _fake_post(url: str, **kwargs: object) -> _GatewayResponse:
            return _GatewayResponse(502, {"error": "bad gateway"}, text='{"error":"bad gateway"}')

        monkeypatch.setattr("pipelines.poster_generate.httpx.post", _fake_post)
        monkeypatch.setenv("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:11436/v1")

        with pytest.raises(RuntimeError, match="Vizier gateway image generation failed"):
            _generate_hero_openai("coffee poster hero", str(tmp_path / "hero.png"))


class TestGenerateHeroFalAi:
    def test_routes_image_generation_through_gateway(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        requests: list[dict[str, object]] = []
        output_path = tmp_path / "hero.png"
        hero_file = tmp_path / "fal-hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        def _fake_run(**kwargs: object) -> dict[str, str]:
            requests.append(dict(kwargs))
            assert kwargs["gateway_headers"]["x-vizier-source"] == "pipeline"
            assert kwargs["gateway_headers"]["x-vizier-modality"] == "image_generation"
            assert kwargs["gateway_headers"]["x-vizier-pipeline-name"] == "poster_generate"
            assert kwargs["gateway_headers"]["x-vizier-pipeline-version"] == "1.0"
            assert kwargs["gateway_headers"]["x-vizier-step-name"] == "hero_generate"
            Path(str(kwargs["output_path"])).write_bytes(hero_file.read_bytes())
            return {"file_path": str(kwargs["output_path"]), "image_url": "https://fal.ai/output/abc.png"}

        monkeypatch.setattr("scripts.visual.generate_image.run", _fake_run)

        hero_path = _generate_hero_falai("coffee poster hero", str(output_path))

        assert hero_path == str(output_path)
        assert output_path.read_bytes() == b"\x89PNG" + b"\x00" * 50
        assert len(requests) == 1
        assert requests[0]["prompt"] == "coffee poster hero"
        assert requests[0]["width"] == 1024
        assert requests[0]["height"] == 1024


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

        assert result["template_used"]
        assert result["width"] == 1080
        assert result["reference_trace"]["lookup_tools_used"] == [
            "search_ui_styles",
            "search_ux_guidelines",
        ]
        assert result["art_direction_plan"]["composition_instruction"]
        trace_payload = json.loads(Path(result["trace_path"]).read_text(encoding="utf-8"))
        assert trace_payload["reference_trace"]["lookup_tools_used"] == [
            "search_ui_styles",
            "search_ux_guidelines",
        ]

        # Verify screenshot was called with HTML containing CSS vars
        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "--bg-color: #3D405B" in html_arg
        assert "--accent-color: #81B29A" in html_arg
        assert "--color-accent: #81B29A" in html_arg
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

    @patch("pipelines.poster_generate._extract_reference_brand_css")
    @patch("pipelines.poster_generate._analyze_reference_image")
    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_reference_image_path_applies_visual_guidance(
        self,
        mock_hero: MagicMock,
        mock_screenshot: MagicMock,
        mock_analyze_reference: MagicMock,
        mock_extract_reference_css: MagicMock,
        tmp_path: Path,
    ) -> None:
        """reference_image_path can drive prompt, template, and theming."""
        reference = tmp_path / "reference.png"
        reference.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        mock_analyze_reference.return_value.style_hint = "warm premium cafe editorial"
        mock_analyze_reference.return_value.avoid_hint = "copying logos or dense layouts"
        mock_analyze_reference.return_value.template_name = "floating-card-square"
        mock_extract_reference_css.return_value = {
            "--bg-color": "#112233",
            "--accent-color": "#DDAA55",
            "--font-headline": "Georgia",
            "--font-body": "Inter",
            "--font-headline-weight": "700",
            "--font-body-weight": "400",
            "--text-color": "#ffffff",
            "--text-muted": "rgba(255, 255, 255, 0.72)",
            "--color-accent": "#DDAA55",
            "--color-accent-end": "#EEE2CC",
            "--color-accent-glow": "#DDAA55",
            "--color-bg": "#112233",
            "--color-text": "#ffffff",
            "--font-heading": "Georgia",
            "--font-weight-heading": "700",
            "--font-weight-body": "400",
            "--letter-spacing-heading": "-0.02em",
            "--letter-spacing-body": "0em",
            "--line-height-heading": "1.1",
            "--line-height-body": "1.5",
        }

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert "warm premium cafe editorial" in prompt
            assert "Use the provided reference image as inspiration only" in prompt
            assert "copying logos or dense layouts" in prompt
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Weekend Brunch",
            body="Fresh flavors and good coffee",
            reference_image_path=str(reference),
            output_path=str(tmp_path / "poster.png"),
        )

        assert result["template_used"] == "floating-card-square"
        html_arg = mock_screenshot.call_args[1]["html"] if "html" in mock_screenshot.call_args[1] else mock_screenshot.call_args[0][0]
        assert "--bg-color: #112233;" in html_arg
        assert "--accent-color: #DDAA55;" in html_arg

    def test_missing_reference_image_raises(self) -> None:
        """Unknown reference image path should fail clearly."""
        with pytest.raises(FileNotFoundError, match="Reference image not found"):
            run(
                headline="Test",
                body="Body",
                reference_image_path="/tmp/does-not-exist-reference.png",
            )

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    @patch("pipelines.poster_brief.llm_chat")
    def test_freeform_brief_is_normalized_before_rendering(
        self,
        mock_llm: MagicMock,
        mock_hero: MagicMock,
        mock_screenshot: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A raw brief can drive copy, template, and image direction."""
        alternate_template = next(
            template.name
            for template in list_templates()
            if template.name != "social-post"
        )
        mock_llm.return_value = json.dumps(
            {
                "campaign_angle": "New Year upgrade momentum",
                "audience": "Apple customers ready for a desktop refresh",
                "visual_direction": "Premium minimal launch poster with a large centered hero",
                "hero_focus": "Mac mini M4 floating in soft studio light",
                "headline": "New year. New power.",
                "body": "Meet Mac mini with M4.",
                "cta": "Learn more",
                "image_prompt": (
                    "Compact aluminum desktop computer on a soft gradient background, "
                    "premium studio lighting, hero-forward composition, no text, no logos"
                ),
                "template_name": alternate_template,
                "avoid": ["tiny unreadable copy", "muddy dark gradients"],
            }
        )

        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert "premium studio lighting" in prompt
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            brief="I want a New Year Apple-style poster to sell the new Mac mini M4.",
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["template_used"] == alternate_template
        assert result["creative_brief"]["campaign_angle"] == "New Year upgrade momentum"
        assert result["creative_brief"]["headline"] == "New year. New power."
        assert result["creative_brief"]["cta"] == "Learn More"

        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "New year. New power." in html_arg
        assert "Meet Mac mini with M4." in html_arg

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
            assert mode == "falai"
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

        assert result["template_used"]
        assert result["template_reason"]
        assert result["prompt_trace"]["quality_guardrail_parts"]
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

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_logo_image_path_renders_official_logo_overlay(
        self,
        mock_hero: MagicMock,
        mock_screenshot: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An explicit logo asset should render as a separate HTML overlay."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)
        logo_file = tmp_path / "logo.png"
        logo_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Batik Hari Guru",
            body="Edisi premium buatan tangan",
            brand_name="Desa Murni Batik",
            logo_mark="DMB",
            logo_image_path=str(logo_file),
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["logo_rendering"]["mode"] == "asset_overlay"
        assert result["logo_image_path"] == str(logo_file)
        assert result["render_trace"]["logo_asset_overlay"] is True

        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "reactor-logo-overlay" in html_arg
        assert 'alt="Desa Murni Batik logo"' in html_arg
        assert ".logo-mark {" in html_arg
        assert "display: none !important;" in html_arg

    def test_missing_logo_image_path_raises(self) -> None:
        """Unknown logo assets should fail clearly."""
        with pytest.raises(FileNotFoundError, match="Logo image not found"):
            run(
                headline="Test",
                body="Body",
                logo_image_path="/tmp/does-not-exist-logo.png",
                palette=SAMPLE_PALETTE,
                fonts=SAMPLE_FONTS,
            )

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_revision_goals_flow_into_prompt_and_trace(
        self,
        mock_hero: MagicMock,
        mock_screenshot: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Structured revision goals should add explicit prompt guardrails and trace data."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)
        logo_file = tmp_path / "logo.png"
        logo_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert "Only one clear primary headline" in prompt
            assert "Reserve a clean, high-contrast area for the separate official logo overlay" in prompt
            assert "Treat this as a revision of the existing hero-bottom-text-square composition" in prompt
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Selamat Hari Raya",
            body="Celebrate the season together.",
            template_name="hero-bottom-text-square",
            logo_mark="PETRONAS",
            logo_image_path=str(logo_file),
            revision_goals=[
                {
                    "key": "increase_logo_visibility",
                    "category": "change",
                    "label": "Increase logo visibility",
                    "instruction": "Make the logo more visible.",
                },
                {
                    "key": "remove_duplicate_main_headline",
                    "category": "change",
                    "label": "Remove duplicate main headline",
                    "instruction": "Use only one main headline.",
                },
            ],
            preserve_goals=[
                {
                    "key": "preserve_premium_feel",
                    "category": "preserve",
                    "label": "Preserve premium feel",
                    "instruction": "Keep the premium feel.",
                }
            ],
            prior_poster_context={"template_name": "hero-bottom-text-square"},
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["prompt_trace"]["revision_guardrail_parts"]
        assert result["revision_trace"]["change_goals"][0]["key"] == "increase_logo_visibility"
        assert result["revision_trace"]["preserve_goals"][0]["key"] == "preserve_premium_feel"

    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_revision_engine_goal_keys_trigger_same_guardrails(
        self,
        mock_hero: MagicMock,
        mock_screenshot: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Generator should honor the revision engine's goal taxonomy directly."""
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG" + b"\x00" * 50)
        logo_file = tmp_path / "logo.png"
        logo_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            assert "Only one clear primary headline" in prompt
            assert "Reserve a clean, high-contrast area for the separate official logo overlay" in prompt
            assert "Refine hierarchy and spacing" in prompt
            assert "Protect small-screen readability" in prompt
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Selamat Hari Raya",
            body="Celebrate the season together.",
            template_name="hero-bottom-text-square",
            logo_mark="PETRONAS",
            logo_image_path=str(logo_file),
            revision_goals=[
                {
                    "key": "brand_visibility",
                    "category": "change",
                    "label": "Stronger brand visibility",
                    "instruction": "Increase the logo or brand mark prominence with clearer scale, contrast, and placement.",
                },
                {
                    "key": "single_main_headline",
                    "category": "change",
                    "label": "One main headline only",
                    "instruction": "Use one clear primary greeting or headline treatment and remove duplicate headline emphasis.",
                },
                {
                    "key": "cleaner_hierarchy",
                    "category": "change",
                    "label": "Cleaner hierarchy",
                    "instruction": "Tighten the layout hierarchy, reduce wasted space, and keep the composition premium instead of sparse.",
                },
                {
                    "key": "mobile_readability",
                    "category": "change",
                    "label": "Stronger mobile readability",
                    "instruction": "Protect small-screen readability with clearer type scale, contrast, and spacing.",
                },
            ],
            preserve_goals=[
                {
                    "key": "preserve_template_composition",
                    "category": "preserve",
                    "label": "Preserve working composition",
                    "instruction": "Preserve the strongest parts of the existing hero-bottom-text-square composition unless a requested change requires a deliberate layout shift.",
                }
            ],
            prior_poster_context={"template_name": "hero-bottom-text-square"},
            output_path=str(tmp_path / "poster.png"),
            palette=SAMPLE_PALETTE,
            fonts=SAMPLE_FONTS,
        )

        assert result["prompt_trace"]["revision_guardrail_parts"]
        assert result["revision_trace"]["change_goals"][0]["key"] == "brand_visibility"


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    def test_plugin_registers_tool(self) -> None:
        """plugins/poster_tool.py registers poster tools via ctx."""
        from plugins.poster_tool import register

        ctx = MagicMock()
        register(ctx)

        registered = {
            call.kwargs["name"]: call.kwargs
            for call in ctx.register_tool.call_args_list
        }
        assert {
            "generate_poster",
            "prepare_poster_revision",
            "revise_poster_structured",
            "check_poster_revision",
            "resolve_brand_asset",
            "summarize_poster_revision",
            "revise_poster",
        } <= set(registered)
        generate_kwargs = registered["generate_poster"]
        revise_kwargs = registered["revise_poster"]
        prepare_kwargs = registered["prepare_poster_revision"]
        assert generate_kwargs["name"] == "generate_poster"
        assert generate_kwargs["toolset"] == "vizier-visual"
        assert "headline" in generate_kwargs["schema"]["properties"]
        assert "body" in generate_kwargs["schema"]["properties"]
        assert "palette" in generate_kwargs["schema"]["properties"]
        assert "fonts" in generate_kwargs["schema"]["properties"]
        assert revise_kwargs["name"] == "revise_poster"
        assert revise_kwargs["toolset"] == "vizier-visual"
        assert "feedback" in revise_kwargs["schema"]["properties"]
        assert prepare_kwargs["toolset"] == "vizier-visual"
        assert "feedback" in prepare_kwargs["schema"]["properties"]

        ctx.register_hook.assert_called_once()
        hook_args = ctx.register_hook.call_args[0]
        assert hook_args[0] == "on_agent_ready"
        assert callable(hook_args[1])

    def test_schema_supports_client_theming_fields(self) -> None:
        """Schema exposes client-aware poster theming fields."""
        from plugins.poster_tool import GENERATE_POSTER_SCHEMA

        assert "brief" in GENERATE_POSTER_SCHEMA["properties"]
        assert {"required": ["brief"]} in GENERATE_POSTER_SCHEMA["anyOf"]
        assert {"required": ["headline", "body"]} in GENERATE_POSTER_SCHEMA["anyOf"]
        assert "client_id" in GENERATE_POSTER_SCHEMA["properties"]
        assert "style_reference" in GENERATE_POSTER_SCHEMA["properties"]
        assert "reference_image_path" in GENERATE_POSTER_SCHEMA["properties"]
        assert "brand_name" in GENERATE_POSTER_SCHEMA["properties"]
        assert "logo_mark" in GENERATE_POSTER_SCHEMA["properties"]
        assert "brand_css" in GENERATE_POSTER_SCHEMA["properties"]

    def test_generate_poster_is_hidden_in_telegram_assistant_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Telegram assistant mode should hide poster tools until work mode is active."""
        from plugins.poster_tool import register
        from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode

        monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
        clear_telegram_mode()

        ctx = MagicMock()
        register(ctx)

        registered = {
            call.kwargs["name"]: call.kwargs
            for call in ctx.register_tool.call_args_list
        }
        generate_kwargs = registered["generate_poster"]
        revise_kwargs = registered["revise_poster"]
        prepare_kwargs = registered["prepare_poster_revision"]
        assert generate_kwargs["name"] == "generate_poster"
        assert revise_kwargs["name"] == "revise_poster"
        assert generate_kwargs["check_fn"]() is False
        assert revise_kwargs["check_fn"]() is False
        assert prepare_kwargs["check_fn"]() is False

        set_telegram_mode(platform="telegram", mode="vizier_work")
        assert generate_kwargs["check_fn"]() is True
        assert prepare_kwargs["check_fn"]() is True
        assert revise_kwargs["check_fn"]() is False

    def test_revise_poster_becomes_available_once_session_has_prior_poster(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """revise_poster should only appear once the session has a tracked poster."""
        from plugins.poster_tool import register
        from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode
        from plugins.telegram_poster_session import record_poster_result

        monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
        monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-session")
        monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
        clear_telegram_mode()
        set_telegram_mode(platform="telegram", mode="vizier_work")

        ctx = MagicMock()
        register(ctx)
        registered = {
            call.kwargs["name"]: call.kwargs
            for call in ctx.register_tool.call_args_list
        }
        revise_kwargs = registered["revise_poster"]
        assert revise_kwargs["check_fn"]() is False

        record_poster_result(
            tool_name="generate_poster",
            tool_args={"brief": "PETRONAS poster"},
            result_payload={"poster_path": "/tmp/poster.png"},
        )

        assert revise_kwargs["check_fn"]() is True

    @patch("pipelines.poster_generate.run")
    def test_handler_accepts_freeform_brief(
        self,
        mock_run: MagicMock,
    ) -> None:
        """generate_poster accepts a raw brief without requiring structured copy."""
        from plugins.poster_tool import _handle_generate_poster

        mock_run.return_value = {
            "poster_path": "/tmp/poster.png",
            "creative_brief": {"headline": "New year. New power."},
        }

        payload = json.loads(
            _handle_generate_poster(
                {
                    "brief": "Apple New Year Mac mini M4 poster",
                    "palette": SAMPLE_PALETTE,
                    "fonts": SAMPLE_FONTS,
                },
                None,
            )
        )

        assert payload["poster_path"] == "/tmp/poster.png"
        assert payload["creative_brief"]["headline"] == "New year. New power."
        assert mock_run.call_args.kwargs["brief"] == "Apple New Year Mac mini M4 poster"
        assert mock_run.call_args.kwargs["headline"] == ""
        assert mock_run.call_args.kwargs["body"] == ""

    @patch("plugins.poster_tool.record_poster_result")
    @patch("pipelines.poster_generate.run")
    def test_generate_handler_uses_session_reference_image_when_missing(
        self,
        mock_run: MagicMock,
        mock_record: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """generate_poster reuses the active session reference image when available."""
        from plugins.poster_tool import _handle_generate_poster

        monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-session")
        monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

        from plugins.telegram_poster_session import record_reference_image

        record_reference_image("/tmp/reference-sample.png", source="telegram_photo")
        mock_run.return_value = {"poster_path": "/tmp/poster.png"}

        payload = json.loads(
            _handle_generate_poster(
                {
                    "brief": "Make a poster using the current sample",
                    "palette": SAMPLE_PALETTE,
                    "fonts": SAMPLE_FONTS,
                },
                None,
            )
        )

        assert payload["poster_path"] == "/tmp/poster.png"
        assert mock_run.call_args.kwargs["reference_image_path"] == "/tmp/reference-sample.png"
        assert mock_record.called

    @patch("plugins.poster_tool.record_poster_result")
    @patch("plugins.poster_tool.record_feedback_note")
    @patch("pipelines.poster_revision.run")
    def test_revise_handler_uses_latest_session_poster_and_reference_state(
        self,
        mock_revision_run: MagicMock,
        mock_feedback: MagicMock,
        mock_record: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """revise_poster pulls prior poster and reference image state from the session."""
        from plugins.poster_tool import _handle_revise_poster
        from plugins.telegram_poster_session import record_poster_result, record_reference_image

        monkeypatch.setenv("HERMES_SESSION_KEY", "telegram-session")
        monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

        record_reference_image("/tmp/reference-sample.png", source="telegram_photo")
        record_poster_result(
            tool_name="generate_poster",
            tool_args={
                "brief": "PETRONAS Raya poster",
                "template_name": "social-post",
                "palette": SAMPLE_PALETTE,
                "fonts": SAMPLE_FONTS,
            },
            result_payload={
                "poster_path": "/tmp/original-poster.png",
                "trace_path": "/tmp/original-poster.trace.json",
                "creative_brief": {
                    "raw_brief": "PETRONAS Raya poster",
                    "headline": "Selamat Hari Raya",
                    "body": "Celebrate together.",
                    "cta": "Learn more",
                    "image_prompt": "Festive premium background",
                },
            },
        )
        mock_revision_run.return_value = {
            "poster_path": "/tmp/revised-poster.png",
            "revision_plan": {"change_goals": [{"key": "brand_visibility"}]},
        }

        payload = json.loads(
            _handle_revise_poster(
                {"feedback": "Make the logo bigger and keep it premium."},
                None,
            )
        )

        assert payload["poster_path"] == "/tmp/revised-poster.png"
        assert mock_revision_run.call_args.kwargs["reference_image_path"] == "/tmp/reference-sample.png"
        latest_state = mock_revision_run.call_args.kwargs["latest_poster_state"]
        assert latest_state["latest_generated_poster_path"] == "/tmp/original-poster.png"
        assert latest_state["latest_poster_args"]["brief"] == "PETRONAS Raya poster"
        assert mock_feedback.called
        assert mock_record.called
