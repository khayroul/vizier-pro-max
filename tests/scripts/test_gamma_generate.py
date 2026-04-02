"""Tests for Gamma generation wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _mock_response(*, payload: dict[str, object], status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = str(payload)
    response.raise_for_status.return_value = None
    return response


class TestGammaGenerate:
    def test_run_creates_generation_polls_and_downloads_export(self, tmp_path: Path) -> None:
        from scripts.document.gamma_generate import run

        create_response = _mock_response(payload={"generationId": "gen_123"})
        poll_response = _mock_response(
            payload={
                "generationId": "gen_123",
                "status": "completed",
                "gammaUrl": "https://gamma.app/docs/gen_123",
                "exportUrl": "https://gamma.app/export/gen_123.pdf",
                "credits": {"deducted": 15, "remaining": 485},
            }
        )
        download_response = MagicMock()
        download_response.content = b"%PDF-1.4"
        download_response.raise_for_status.return_value = None

        with (
            patch("scripts.document.gamma_generate.ensure_env", return_value=None),
            patch.dict(
                "os.environ",
                {
                    "GAMMA_API_KEY": "test-key",
                    "VIZIER_ALLOWED_ROOTS": str(tmp_path.resolve()),
                },
                clear=True,
            ),
            patch("scripts.document.gamma_generate.httpx.request", side_effect=[create_response, poll_response]) as request_mock,
            patch("scripts.document.gamma_generate.httpx.get", return_value=download_response),
        ):
            result = run(
                input_text="Turn this report into a deck.",
                num_cards=8,
                card_split="auto",
                card_dimensions="16x9",
                text_amount="brief",
                tone="professional",
                audience="executives",
                language="en",
                image_source="aiGenerated",
                image_model="flux-kontext-fast",
                image_style="premium editorial",
                image_style_preset="custom",
                header_footer={"bottomRight": {"type": "text", "value": "Confidential"}},
                sharing_options={"workspaceAccess": "view"},
                output_path=str(tmp_path / "deck.pdf"),
                poll_interval=0.01,
                timeout=5.0,
            )

        assert result["generation_id"] == "gen_123"
        assert result["status"] == "completed"
        assert result["gamma_url"] == "https://gamma.app/docs/gen_123"
        assert result["export_url"] == "https://gamma.app/export/gen_123.pdf"
        assert Path(result["file_path"]).exists()
        create_call = request_mock.call_args_list[0]
        assert create_call.kwargs["headers"]["X-API-KEY"] == "test-key"
        assert create_call.kwargs["json"]["format"] == "presentation"
        assert create_call.kwargs["json"]["textMode"] == "condense"
        assert create_call.kwargs["json"]["numCards"] == 8
        assert create_call.kwargs["json"]["cardSplit"] == "auto"
        assert create_call.kwargs["json"]["cardOptions"]["dimensions"] == "16x9"
        assert create_call.kwargs["json"]["imageOptions"]["source"] == "aiGenerated"
        assert create_call.kwargs["json"]["imageOptions"]["model"] == "flux-kontext-fast"
        assert create_call.kwargs["json"]["imageOptions"]["style"] == "premium editorial"
        assert create_call.kwargs["json"]["imageOptions"]["stylePreset"] == "custom"
        assert create_call.kwargs["json"]["textOptions"]["amount"] == "brief"
        assert create_call.kwargs["json"]["textOptions"]["tone"] == "professional"
        assert create_call.kwargs["json"]["textOptions"]["language"] == "en"
        assert create_call.kwargs["json"]["sharingOptions"]["workspaceAccess"] == "view"

    def test_run_supports_template_generation(self, tmp_path: Path) -> None:
        from scripts.document.gamma_generate import run

        create_response = _mock_response(payload={"generationId": "gen_tpl"})
        poll_response = _mock_response(
            payload={
                "generationId": "gen_tpl",
                "status": "completed",
                "gammaUrl": "https://gamma.app/docs/gen_tpl",
                "exportUrl": "https://gamma.app/export/gen_tpl.pptx",
                "warnings": ["theme ignored"],
            }
        )
        download_response = MagicMock()
        download_response.content = b"PPTX"
        download_response.raise_for_status.return_value = None

        with (
            patch("scripts.document.gamma_generate.ensure_env", return_value=None),
            patch.dict(
                "os.environ",
                {
                    "GAMMA_API_KEY": "test-key",
                    "VIZIER_ALLOWED_ROOTS": str(tmp_path.resolve()),
                },
                clear=True,
            ),
            patch("scripts.document.gamma_generate.httpx.request", side_effect=[create_response, poll_response]) as request_mock,
            patch("scripts.document.gamma_generate.httpx.get", return_value=download_response),
        ):
            result = run(
                input_text="Use the attached campaign content.",
                template_gamma_id="gamma_template_123",
                template_prompt="Turn this into a polished board deck.",
                theme_id="theme_1",
                folder_ids=["folder_1"],
                export_as="pptx",
                sharing_options={"externalAccess": "noAccess"},
                output_path=str(tmp_path / "deck.pptx"),
                poll_interval=0.01,
                timeout=5.0,
            )

        assert result["request_mode"] == "from_template"
        assert result["warnings"] == ["theme ignored"]
        create_call = request_mock.call_args_list[0]
        assert create_call.args[1].endswith("/generations/from-template")
        assert create_call.kwargs["json"]["gammaId"] == "gamma_template_123"
        assert "polished board deck" in create_call.kwargs["json"]["prompt"]
        assert create_call.kwargs["json"]["themeId"] == "theme_1"
        assert create_call.kwargs["json"]["folderIds"] == ["folder_1"]
        assert create_call.kwargs["json"]["sharingOptions"]["externalAccess"] == "noAccess"

    def test_run_raises_when_generation_fails(self) -> None:
        from scripts.document.gamma_generate import run

        create_response = _mock_response(payload={"generationId": "gen_999"})
        failed_response = _mock_response(
            payload={
                "generationId": "gen_999",
                "status": "failed",
                "errorMessage": "Insufficient credits",
            }
        )
        with (
            patch("scripts.document.gamma_generate.ensure_env", return_value=None),
            patch.dict("os.environ", {"GAMMA_API_KEY": "test-key"}, clear=True),
            patch("scripts.document.gamma_generate.httpx.request", side_effect=[create_response, failed_response]),
            pytest.raises(RuntimeError, match="Insufficient credits"),
        ):
            run(input_text="Create a deck", poll_interval=0.01, timeout=1.0)

    def test_run_rejects_path_outside_allowed_roots(self, tmp_path: Path) -> None:
        from scripts.document.gamma_generate import run

        create_response = _mock_response(payload={"generationId": "gen_123"})
        poll_response = _mock_response(
            payload={
                "generationId": "gen_123",
                "status": "completed",
                "gammaUrl": "https://gamma.app/docs/gen_123",
                "exportUrl": "https://gamma.app/export/gen_123.pdf",
            }
        )
        download_response = MagicMock()
        download_response.content = b"%PDF-1.4"
        download_response.raise_for_status.return_value = None

        with (
            patch("scripts.document.gamma_generate.ensure_env", return_value=None),
            patch.dict("os.environ", {"GAMMA_API_KEY": "test-key"}, clear=True),
            patch("scripts.document.gamma_generate.httpx.request", side_effect=[create_response, poll_response]),
            patch("scripts.document.gamma_generate.httpx.get", return_value=download_response),
            pytest.raises(ValueError, match="escapes allowed directory"),
        ):
            run(
                input_text="Create a deck",
                output_path=str(tmp_path.parent / "outside.pdf"),
                poll_interval=0.01,
                timeout=5.0,
            )

    def test_list_themes_and_folders(self) -> None:
        from scripts.document.gamma_generate import list_folders, list_themes

        themes_response = _mock_response(payload={"data": [{"id": "theme_1", "name": "Brand"}], "hasMore": False})
        folders_response = _mock_response(payload={"data": [{"id": "folder_1", "name": "Marketing"}], "hasMore": False})

        with (
            patch("scripts.document.gamma_generate.ensure_env", return_value=None),
            patch.dict("os.environ", {"GAMMA_API_KEY": "test-key"}, clear=True),
            patch("scripts.document.gamma_generate.httpx.request", side_effect=[themes_response, folders_response]),
        ):
            themes = list_themes(query="brand")
            folders = list_folders(query="marketing")

        assert themes["data"][0]["id"] == "theme_1"
        assert folders["data"][0]["id"] == "folder_1"

    def test_run_requires_api_key(self) -> None:
        from scripts.document.gamma_generate import run

        with patch("scripts.document.gamma_generate.ensure_env", return_value=None), patch.dict("os.environ", {}, clear=True), pytest.raises(RuntimeError, match="GAMMA_API_KEY"):
            run(input_text="Create a deck")
