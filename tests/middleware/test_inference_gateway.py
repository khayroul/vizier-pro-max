"""Tests for the local Vizier inference gateway."""
from __future__ import annotations

from typing import Any

import pytest

from middleware.inference_gateway import (
    extract_metadata,
    gateway_models_payload,
    proxy_chat_completion,
    proxy_image_generation,
)


class _MockResponse:
    def __init__(
        self,
        status_code: int,
        body: dict[str, Any],
        *,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else str(body)
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = self.text.encode("utf-8")

    def json(self) -> dict[str, Any]:
        return self._body


def test_extract_metadata_defaults_to_hermes() -> None:
    metadata = extract_metadata({})

    assert metadata.source == "hermes"
    assert metadata.modality == "chat"


def test_gateway_models_payload_lists_primary_and_fallback() -> None:
    payload = gateway_models_payload()

    ids = [entry["id"] for entry in payload["data"]]
    assert "gpt-5.4-mini" in ids
    assert "qwen3.5:9b" in ids


def test_proxy_chat_completion_logs_openai_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[dict[str, Any]] = []

    def _fake_record(**kwargs: Any) -> int:
        logged.append(kwargs)
        return 1

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        assert "api.openai.com" in url
        return _MockResponse(
            200,
            {
                "model": "gpt-5.4-mini",
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4},
            },
        )

    monkeypatch.setattr("middleware.inference_gateway.record_external_usage", _fake_record)
    monkeypatch.setattr("middleware.inference_gateway.httpx.post", _fake_post)
    monkeypatch.setenv("VIZIER_UPSTREAM_OPENAI_API_KEY", "sk-test")

    response = proxy_chat_completion(
        request_body={
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
        request_headers={
            "x-vizier-source": "pipeline",
            "x-vizier-client-id": "client_a",
            "x-vizier-deliverable-id": "d1",
            "x-vizier-modality": "chat",
        },
    )

    assert response.status_code == 200
    assert len(logged) == 1
    assert logged[0]["provider_name"] == "openai"
    assert logged[0]["source"] == "pipeline"
    assert logged[0]["client_id"] == "client_a"
    assert logged[0]["status"] == "succeeded"
    assert logged[0]["input_tokens"] == 9
    assert logged[0]["output_tokens"] == 4


def test_proxy_chat_completion_falls_back_to_ollama_on_openai_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[dict[str, Any]] = []

    def _fake_record(**kwargs: Any) -> int:
        logged.append(kwargs)
        return len(logged)

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        if "api.openai.com" in url:
            return _MockResponse(500, {"error": "upstream unavailable"}, text='{"error":"upstream unavailable"}')
        if "localhost:11434" in url:
            return _MockResponse(
                200,
                {
                    "message": {"content": "fallback answer"},
                    "prompt_eval_count": 11,
                    "eval_count": 7,
                },
            )
        msg = f"Unexpected URL: {url}"
        raise AssertionError(msg)

    monkeypatch.setattr("middleware.inference_gateway.record_external_usage", _fake_record)
    monkeypatch.setattr("middleware.inference_gateway.httpx.post", _fake_post)
    monkeypatch.setenv("VIZIER_UPSTREAM_OPENAI_API_KEY", "sk-test")

    response = proxy_chat_completion(
        request_body={
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
        request_headers={},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["choices"][0]["message"]["content"] == "fallback answer"
    assert len(logged) == 2
    assert logged[0]["provider_name"] == "openai"
    assert logged[0]["status"] == "failed"
    assert logged[1]["provider_name"] == "ollama"
    assert logged[1]["status"] == "succeeded"
    assert logged[1]["source"] == "hermes"


def test_proxy_chat_completion_rejects_streaming() -> None:
    with pytest.raises(ValueError, match="Streaming is not supported"):
        proxy_chat_completion(
            request_body={
                "model": "gpt-5.4-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
            request_headers={},
        )


def test_proxy_chat_completion_bubbles_non_chat_openai_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[dict[str, Any]] = []

    def _fake_record(**kwargs: Any) -> int:
        logged.append(kwargs)
        return len(logged)

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        return _MockResponse(500, {"error": "upstream unavailable"}, text='{"error":"upstream unavailable"}')

    monkeypatch.setattr("middleware.inference_gateway.record_external_usage", _fake_record)
    monkeypatch.setattr("middleware.inference_gateway.httpx.post", _fake_post)
    monkeypatch.setenv("VIZIER_UPSTREAM_OPENAI_API_KEY", "sk-test")

    response = proxy_chat_completion(
        request_body={
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
        request_headers={"x-vizier-modality": "vision"},
    )

    assert response.status_code == 500
    assert len(logged) == 1
    assert logged[0]["provider_name"] == "openai"
    assert logged[0]["status"] == "failed"


def test_proxy_image_generation_logs_openai_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[dict[str, Any]] = []

    def _fake_record(**kwargs: Any) -> int:
        logged.append(kwargs)
        return len(logged)

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        assert "api.openai.com" in url
        assert kwargs["json"]["model"] == "gpt-image-1"
        return _MockResponse(
            200,
            {
                "model": "gpt-image-1",
                "data": [{"b64_json": "ZmFrZQ=="}],
                "usage": {"prompt_tokens": 321},
            },
        )

    monkeypatch.setattr("middleware.inference_gateway.record_external_usage", _fake_record)
    monkeypatch.setattr("middleware.inference_gateway.httpx.post", _fake_post)
    monkeypatch.setenv("VIZIER_UPSTREAM_OPENAI_API_KEY", "sk-test")

    response = proxy_image_generation(
        request_body={
            "model": "gpt-image-1",
            "prompt": "coffee poster hero",
            "size": "1024x1024",
        },
        request_headers={
            "x-vizier-source": "pipeline",
            "x-vizier-client-id": "client_a",
            "x-vizier-deliverable-id": "d1",
            "x-vizier-modality": "image_generation",
        },
    )

    assert response.status_code == 200
    assert len(logged) == 1
    assert logged[0]["provider_name"] == "openai"
    assert logged[0]["source"] == "pipeline"
    assert logged[0]["modality"] == "image_generation"
    assert logged[0]["client_id"] == "client_a"
    assert logged[0]["status"] == "succeeded"
    assert logged[0]["input_tokens"] == 321
    assert logged[0]["response_text"] == '{"image_count": 1, "first_kind": "b64_json"}'


def test_proxy_image_generation_logs_openai_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[dict[str, Any]] = []

    def _fake_record(**kwargs: Any) -> int:
        logged.append(kwargs)
        return len(logged)

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        return _MockResponse(500, {"error": "upstream unavailable"}, text='{"error":"upstream unavailable"}')

    monkeypatch.setattr("middleware.inference_gateway.record_external_usage", _fake_record)
    monkeypatch.setattr("middleware.inference_gateway.httpx.post", _fake_post)
    monkeypatch.setenv("VIZIER_UPSTREAM_OPENAI_API_KEY", "sk-test")

    response = proxy_image_generation(
        request_body={
            "model": "gpt-image-1",
            "prompt": "coffee poster hero",
            "size": "1024x1024",
        },
        request_headers={"x-vizier-modality": "image_generation"},
    )

    assert response.status_code == 500
    assert len(logged) == 1
    assert logged[0]["provider_name"] == "openai"
    assert logged[0]["status"] == "failed"
    assert logged[0]["failure_reason"] == "http_status:500"
