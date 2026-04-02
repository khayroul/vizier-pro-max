"""Tests for the gateway-backed LLM client."""
from __future__ import annotations

from typing import Any

import pytest

from adapter.llm_client import chat
from middleware.deliverable_context import (
    clear_context,
    set_pipeline_step,
    start_deliverable,
)


class _MockResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


@pytest.fixture(autouse=True)
def _clear_context() -> None:
    clear_context()
    yield
    clear_context()


def test_chat_calls_local_gateway_with_vizier_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        seen["url"] = url
        seen["headers"] = kwargs.get("headers") or {}
        seen["json"] = kwargs.get("json") or {}
        return _MockResponse(
            200,
            {
                "choices": [{"message": {"content": "gateway answer"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr("adapter.llm_client.httpx.post", _fake_post)
    monkeypatch.setenv("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:11436/v1")

    deliverable_id = start_deliverable(client_id="client_a")
    set_pipeline_step("draft", "content_generate", "1.0")
    result = chat(messages=[{"role": "user", "content": "hello"}], max_tokens=77)

    assert result == "gateway answer"
    assert seen["url"] == "http://127.0.0.1:11436/v1/chat/completions"
    assert seen["json"]["model"] == "gpt-5.4-mini"
    assert seen["json"]["max_completion_tokens"] == 77
    assert seen["headers"]["x-vizier-source"] == "pipeline"
    assert seen["headers"]["x-vizier-deliverable-id"] == deliverable_id
    assert seen["headers"]["x-vizier-client-id"] == "client_a"
    assert seen["headers"]["x-vizier-pipeline-name"] == "content_generate"
    assert seen["headers"]["x-vizier-step-name"] == "draft"
    assert seen["headers"]["x-vizier-modality"] == "chat"


def test_chat_marks_vision_requests_for_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        seen["headers"] = kwargs.get("headers") or {}
        return _MockResponse(
            200,
            {
                "choices": [{"message": {"content": "A test image"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr("adapter.llm_client.httpx.post", _fake_post)

    result = chat(
        messages=[
            {"role": "system", "content": "You are a vision model."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image:"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            },
        ],
        max_tokens=100,
    )

    assert result == "A test image"
    assert seen["headers"]["x-vizier-modality"] == "vision"


def test_chat_returns_none_when_gateway_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_post(url: str, **kwargs: Any) -> _MockResponse:
        return _MockResponse(502, {"error": "gateway down"})

    monkeypatch.setattr("adapter.llm_client.httpx.post", _fake_post)

    result = chat(messages=[{"role": "user", "content": "hello"}], max_tokens=100)

    assert result is None
