"""Tests for telegram_marketing_bot helpers."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.delivery.telegram_marketing_bot import (
    _build_pipeline_args,
    collect_client_files,
    generate_marketing_package,
    send_marketing_package,
)


class TestTelegramMarketingBot:
    def test_build_pipeline_args_sets_output_root(self, tmp_path: Path) -> None:
        args = _build_pipeline_args(
            brief="Create a Ramadan campaign for our bakery.",
            client_id="dmb",
            output_root=str(tmp_path),
        )

        assert args["brief"] == "Create a Ramadan campaign for our bakery."
        assert args["client_id"] == "dmb"
        assert args["package_mode"] == "document_bundle"
        assert args["generate_posters"] is True
        assert Path(args["output_dir"]).parent == tmp_path

    def test_generate_marketing_package_calls_run_pipeline(self, tmp_path: Path) -> None:
        fake_payload = {
            "status": "completed",
            "title": "Bakery Marketing Plan",
            "document_count": 2,
        }
        with patch(
            "scripts.delivery.telegram_marketing_bot.run_pipeline",
            return_value=json.dumps(fake_payload),
        ) as mock_run_pipeline:
            result = generate_marketing_package(
                brief="Create a Ramadan campaign for our bakery.",
                client_id="dmb",
                output_root=str(tmp_path),
            )

        assert result["title"] == "Bakery Marketing Plan"
        call_args = mock_run_pipeline.call_args.args[0]
        assert call_args["name"] == "marketing_plan_generate"
        assert call_args["args"]["client_id"] == "dmb"

    def test_collect_client_files_returns_documents_and_posters(self) -> None:
        result = {
            "documents": [
                {"pdf_path": "/tmp/strategy.pdf"},
                {"pdf_path": "/tmp/creative.pdf"},
            ],
            "operational_assets": {
                "client_poster_paths": ["/tmp/poster-1.png", "/tmp/poster-2.png"],
            },
        }

        files = collect_client_files(result)

        assert files == [
            "/tmp/strategy.pdf",
            "/tmp/creative.pdf",
            "/tmp/poster-1.png",
            "/tmp/poster-2.png",
        ]

    def test_send_marketing_package_sends_summary_and_files(self) -> None:
        result = {
            "title": "Bakery Marketing Plan",
            "document_count": 2,
            "poster_count": 2,
            "documents": [
                {"pdf_path": "/tmp/strategy.pdf"},
                {"pdf_path": "/tmp/creative.pdf"},
            ],
            "operational_assets": {
                "client_poster_paths": ["/tmp/poster-1.png"],
            },
        }

        with patch(
            "scripts.delivery.telegram_marketing_bot.send_telegram_run"
        ) as mock_send:
            send_marketing_package(chat_id="12345", result=result)

        assert mock_send.call_count == 4
        assert mock_send.call_args_list[0].kwargs["text"].startswith(
            "Bakery Marketing Plan is ready."
        )
        assert mock_send.call_args_list[1].kwargs["file_path"] == "/tmp/strategy.pdf"
