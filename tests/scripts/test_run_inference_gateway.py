"""Tests for the local inference gateway launcher."""
from __future__ import annotations

from scripts.delivery import run_inference_gateway


def test_prepare_gateway_env_promotes_legacy_openai_key(
    monkeypatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        run_inference_gateway,
        "ensure_env",
        lambda **kwargs: calls.append(kwargs.get("override_keys")),
    )
    monkeypatch.delenv("VIZIER_UPSTREAM_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")

    run_inference_gateway._prepare_gateway_env()

    assert calls and "OPENAI_API_KEY" in calls[0]
    assert "OPENAI_API_KEY" not in run_inference_gateway.os.environ
    assert run_inference_gateway.os.environ["VIZIER_UPSTREAM_OPENAI_API_KEY"] == "sk-legacy"


def test_prepare_gateway_env_keeps_explicit_upstream_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(run_inference_gateway, "ensure_env", lambda **kwargs: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    monkeypatch.setenv("VIZIER_UPSTREAM_OPENAI_API_KEY", "sk-upstream")

    run_inference_gateway._prepare_gateway_env()

    assert "OPENAI_API_KEY" not in run_inference_gateway.os.environ
    assert run_inference_gateway.os.environ["VIZIER_UPSTREAM_OPENAI_API_KEY"] == "sk-upstream"
