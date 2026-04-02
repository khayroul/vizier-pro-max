"""Client config integration tests for poster_generate."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pipelines.poster_generate import run


class TestPosterClientIntegration:
    @patch("pipelines.poster_generate._screenshot")
    @patch("pipelines.poster_generate._generate_hero")
    def test_client_id_applies_defaults_and_brand_css(
        self, mock_hero: MagicMock, mock_screenshot: MagicMock, tmp_path: Path
    ) -> None:
        hero_file = tmp_path / "hero.png"
        hero_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def fake_hero(prompt: str, output_path: str, mode: str) -> str:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(hero_file.read_bytes())
            return output_path

        mock_hero.side_effect = fake_hero
        mock_screenshot.return_value = None

        result = run(
            headline="Batik Hari Guru",
            body="Edisi premium buatan tangan",
            client_id="dmb",
            output_path=str(tmp_path / "poster.png"),
        )

        assert result["template_used"] == "editorial-split-square"
        assert result["image_mode"] == "openai"
        assert result["brand_name"] == "Desa Murni Batik"
        assert result["logo_mark"] == "DMB"

        call_args = mock_screenshot.call_args
        html_arg = call_args[1]["html"] if "html" in call_args[1] else call_args[0][0]
        assert "--bg-color: #2C1810;" in html_arg
        assert "--color-bg: #2C1810;" in html_arg
        assert "Desa Murni Batik" in html_arg
        assert "DMB" in html_arg
