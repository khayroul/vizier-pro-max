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
    _inject_slots,
    _parse_template,
    _resolve_template,
    _to_data_uri,
    list_templates,
    run,
)


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
        """list_templates returns at least social-post."""
        templates = list_templates()
        names = [t.name for t in templates]
        assert "social-post" in names


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
        assert req.template_name == "social-post"
        assert req.image_mode == "openai"


# ---------------------------------------------------------------------------
# Full pipeline (mocked AI + Playwright)
# ---------------------------------------------------------------------------


class TestRunPipeline:
    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_full_pipeline_openai(
        self, mock_hero: MagicMock, mock_screenshot: MagicMock, tmp_path: Path
    ) -> None:
        """Full pipeline: hero generation + template render."""
        # Mock hero generation to write a fake PNG
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Hari Raya Sale",
            body="Get 50% off all items this festive season",
            cta="Shop Now",
            image_prompt="festive Hari Raya background",
            output_path=str(tmp_path / "poster.png"),
        )

        assert result["template_used"] == "social-post"
        assert result["width"] == 1080
        assert result["height"] == 1080
        assert result["image_mode"] == "openai"
        assert "poster_path" in result
        assert "hero_path" in result

        mock_hero.assert_called_once()
        mock_screenshot.assert_called_once()

        # Verify screenshot was called with injected HTML containing the headline
        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "Hari Raya Sale" in html_arg

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
        )

        assert result["image_mode"] == "falai"

    def test_invalid_template_raises(self) -> None:
        """Unknown template_name raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            run(
                headline="Test",
                body="Body",
                template_name="nonexistent",
            )

    def test_invalid_mode_raises(self) -> None:
        """Invalid image_mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid image_mode"):
            run(
                headline="Test",
                body="Body",
                image_mode="dalle",
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

        ctx.register_hook.assert_called_once()
        hook_args = ctx.register_hook.call_args[0]
        assert hook_args[0] == "on_agent_ready"
        assert callable(hook_args[1])
