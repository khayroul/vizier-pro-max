"""Local OpenAI-compatible inference gateway for Vizier metering.

This is the hard accounting boundary for model traffic. Hermes and shared
Vizier clients should point at this local gateway instead of talking to
providers directly.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

import httpx

from middleware.cost_ledger import record_external_usage

try:
    import structlog
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python envs
    structlog = None

logger = (
    structlog.get_logger(__name__) if structlog is not None
    else logging.getLogger(__name__)
)


@dataclass(frozen=True)
class GatewayMetadata:
    """Vizier request context forwarded as HTTP headers."""

    source: str = "hermes"
    session_id: str | None = None
    deliverable_id: str | None = None
    client_id: str | None = None
    pipeline_name: str | None = None
    pipeline_version: str | None = None
    step_name: str | None = None
    modality: str = "chat"


def default_gateway_base_url() -> str:
    """Return the local OpenAI-compatible gateway base URL."""
    return os.environ.get("VIZIER_GATEWAY_BASE_URL", "http://127.0.0.1:11436/v1").rstrip("/")


def default_openai_base_url() -> str:
    """Return the upstream OpenAI base URL."""
    return os.environ.get("VIZIER_UPSTREAM_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def default_openai_api_key() -> str:
    """Return the upstream OpenAI API key."""
    return (
        os.environ.get("VIZIER_UPSTREAM_OPENAI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )


def default_openai_model() -> str:
    """Return the primary cloud model name exposed by the gateway."""
    return os.environ.get("VIZIER_LLM_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini"


def default_ollama_base_url() -> str:
    """Return the upstream Ollama base URL."""
    return os.environ.get("VIZIER_UPSTREAM_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def default_ollama_model() -> str:
    """Return the local fallback model name exposed by the gateway."""
    return os.environ.get("VIZIER_FALLBACK_MODEL", "qwen3.5:9b").strip() or "qwen3.5:9b"


def gateway_models_payload() -> dict[str, Any]:
    """Return a minimal OpenAI-compatible /v1/models response."""
    return {
        "object": "list",
        "data": [
            {
                "id": default_openai_model(),
                "object": "model",
                "created": 0,
                "owned_by": "vizier-gateway",
            },
            {
                "id": default_ollama_model(),
                "object": "model",
                "created": 0,
                "owned_by": "vizier-gateway",
            },
        ],
    }


def extract_metadata(headers: Mapping[str, str]) -> GatewayMetadata:
    """Extract Vizier request metadata from headers."""
    normalized = {str(key).lower(): value for key, value in headers.items()}
    return GatewayMetadata(
        source=(normalized.get("x-vizier-source") or "hermes").strip() or "hermes",
        session_id=normalized.get("x-vizier-session-id") or None,
        deliverable_id=normalized.get("x-vizier-deliverable-id") or None,
        client_id=normalized.get("x-vizier-client-id") or None,
        pipeline_name=normalized.get("x-vizier-pipeline-name") or None,
        pipeline_version=normalized.get("x-vizier-pipeline-version") or None,
        step_name=normalized.get("x-vizier-step-name") or None,
        modality=(normalized.get("x-vizier-modality") or "chat").strip() or "chat",
    )


def _safe_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _response_text_from_openai_body(body: dict[str, Any]) -> str | None:
    choices = body.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if content is None:
        return None
    return _safe_json(content)


def _response_text_from_ollama_body(body: dict[str, Any]) -> str | None:
    message = body.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if content is None:
        return None
    return _safe_json(content)


def _image_response_summary(body: Mapping[str, Any]) -> str:
    """Return a compact, non-binary summary for image-generation ledger rows."""
    data = body.get("data") or []
    first_item = data[0] if isinstance(data, list) and data else {}
    first_kind = "none"
    if isinstance(first_item, Mapping):
        if first_item.get("b64_json"):
            first_kind = "b64_json"
        elif first_item.get("url"):
            first_kind = "url"
    return _safe_json({"image_count": len(data) if isinstance(data, list) else 0, "first_kind": first_kind})


def _log_attempt(
    *,
    metadata: GatewayMetadata,
    provider_name: str,
    model: str,
    prompt_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    response_text: str | None = None,
    latency_ms: int = 0,
    status: str,
    failure_reason: str | None = None,
) -> int:
    return record_external_usage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        prompt_text=prompt_text,
        response_text=response_text,
        latency_ms=latency_ms,
        deliverable_id=metadata.deliverable_id,
        client_id=metadata.client_id,
        pipeline_name=metadata.pipeline_name,
        step_name=metadata.step_name,
        pipeline_version=metadata.pipeline_version,
        provider_name=provider_name,
        source=metadata.source,
        modality=metadata.modality,
        status=status,
        failure_reason=failure_reason,
    )


def _should_route_to_ollama(request_body: Mapping[str, Any]) -> bool:
    model = str(request_body.get("model") or "").strip()
    if not model:
        return False
    return model == default_ollama_model() or model.startswith("qwen")


def _should_fallback_to_ollama(metadata: GatewayMetadata, response: httpx.Response) -> bool:
    return metadata.modality == "chat" and response.status_code >= 500


def _ollama_payload_from_openai_request(request_body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "model": default_ollama_model(),
        "messages": request_body.get("messages", []),
        "stream": False,
        "options": {"num_ctx": 4096},
        "think": False,
    }


def _openai_payload_from_ollama_response(
    *,
    request_body: Mapping[str, Any],
    response_body: Mapping[str, Any],
) -> dict[str, Any]:
    prompt_tokens = int(response_body.get("prompt_eval_count", 0) or 0)
    completion_tokens = int(response_body.get("eval_count", 0) or 0)
    content = _response_text_from_ollama_body(dict(response_body)) or ""
    return {
        "id": f"chatcmpl-vizier-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(request_body.get("model") or default_ollama_model()),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _proxy_openai_chat_completion(
    *,
    request_body: dict[str, Any],
    metadata: GatewayMetadata,
    timeout: float,
) -> httpx.Response:
    start = time.monotonic()
    api_key = default_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or VIZIER_UPSTREAM_OPENAI_API_KEY is required for gateway upstream access")

    response = httpx.post(
        f"{default_openai_base_url()}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=request_body,
        timeout=timeout,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    prompt_text = _safe_json(request_body.get("messages", []))

    if response.status_code == 200:
        body = response.json()
        usage = body.get("usage") or {}
        _log_attempt(
            metadata=metadata,
            provider_name="openai",
            model=str(body.get("model") or request_body.get("model") or default_openai_model()),
            prompt_text=prompt_text,
            input_tokens=int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
            output_tokens=int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
            response_text=_response_text_from_openai_body(body),
            latency_ms=latency_ms,
            status="succeeded",
        )
        return response

    failure_reason = f"http_status:{response.status_code}"
    _log_attempt(
        metadata=metadata,
        provider_name="openai",
        model=str(request_body.get("model") or default_openai_model()),
        prompt_text=prompt_text,
        response_text=response.text,
        latency_ms=latency_ms,
        status="failed",
        failure_reason=failure_reason,
    )
    return response


def _proxy_ollama_chat_completion(
    *,
    request_body: dict[str, Any],
    metadata: GatewayMetadata,
    timeout: float,
) -> httpx.Response:
    start = time.monotonic()
    response = httpx.post(
        f"{default_ollama_base_url()}/api/chat",
        json=_ollama_payload_from_openai_request(request_body),
        timeout=max(timeout, 120.0),
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    prompt_text = _safe_json(request_body.get("messages", []))

    if response.status_code == 200:
        body = response.json()
        converted = _openai_payload_from_ollama_response(
            request_body=request_body,
            response_body=body,
        )
        usage = converted.get("usage") or {}
        _log_attempt(
            metadata=metadata,
            provider_name="ollama",
            model=str(converted.get("model") or default_ollama_model()),
            prompt_text=prompt_text,
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            response_text=_response_text_from_openai_body(converted),
            latency_ms=latency_ms,
            status="succeeded",
        )
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
            json=converted,
        )

    failure_reason = f"http_status:{response.status_code}"
    _log_attempt(
        metadata=metadata,
        provider_name="ollama",
        model=str(request_body.get("model") or default_ollama_model()),
        prompt_text=prompt_text,
        response_text=response.text,
        latency_ms=latency_ms,
        status="failed",
        failure_reason=failure_reason,
    )
    return response


def proxy_image_generation(
    *,
    request_body: dict[str, Any],
    request_headers: Mapping[str, str],
    timeout: float = 90.0,
) -> httpx.Response:
    """Forward one image-generation request upstream and log usage."""
    metadata = extract_metadata(request_headers)
    start = time.monotonic()
    api_key = default_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or VIZIER_UPSTREAM_OPENAI_API_KEY is required for gateway upstream access")

    response = httpx.post(
        f"{default_openai_base_url()}/images/generations",
        headers={"Authorization": f"Bearer {api_key}"},
        json=request_body,
        timeout=timeout,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    prompt_text = _safe_json({"prompt": request_body.get("prompt"), "size": request_body.get("size"), "model": request_body.get("model")})

    if response.status_code == 200:
        body = response.json()
        usage = body.get("usage") or {}
        input_tokens = int(
            usage.get("prompt_tokens", usage.get("input_tokens", usage.get("total_tokens", 0))) or 0
        )
        output_tokens = int(
            usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
        )
        _log_attempt(
            metadata=metadata,
            provider_name="openai",
            model=str(body.get("model") or request_body.get("model") or "gpt-image-1"),
            prompt_text=prompt_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_text=_image_response_summary(body),
            latency_ms=latency_ms,
            status="succeeded",
        )
        return response

    _log_attempt(
        metadata=metadata,
        provider_name="openai",
        model=str(request_body.get("model") or "gpt-image-1"),
        prompt_text=prompt_text,
        response_text=response.text,
        latency_ms=latency_ms,
        status="failed",
        failure_reason=f"http_status:{response.status_code}",
    )
    return response


def proxy_chat_completion(
    *,
    request_body: dict[str, Any],
    request_headers: Mapping[str, str],
    timeout: float = 60.0,
) -> httpx.Response:
    """Forward one non-streaming chat completion request upstream and log usage."""
    metadata = extract_metadata(request_headers)

    if request_body.get("stream"):
        raise ValueError("Streaming is not supported by the Vizier inference gateway yet")

    if _should_route_to_ollama(request_body):
        return _proxy_ollama_chat_completion(
            request_body=request_body,
            metadata=metadata,
            timeout=timeout,
        )

    try:
        openai_response = _proxy_openai_chat_completion(
            request_body=request_body,
            metadata=metadata,
            timeout=timeout,
        )
    except (RuntimeError, httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
        _log_attempt(
            metadata=metadata,
            provider_name="openai",
            model=str(request_body.get("model") or default_openai_model()),
            prompt_text=_safe_json(request_body.get("messages", [])),
            latency_ms=0,
            status="failed",
            failure_reason=f"{type(exc).__name__}: {exc}",
        )
        if metadata.modality != "chat":
            raise
        return _proxy_ollama_chat_completion(
            request_body=request_body,
            metadata=metadata,
            timeout=timeout,
        )

    if openai_response.status_code == 200 or not _should_fallback_to_ollama(metadata, openai_response):
        return openai_response

    return _proxy_ollama_chat_completion(
        request_body=request_body,
        metadata=metadata,
        timeout=timeout,
    )


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 11436,
    timeout: float = 60.0,
) -> None:
    """Run the local inference gateway."""

    class _GatewayHandler(BaseHTTPRequestHandler):
        server_version = "VizierInferenceGateway/0.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/health", "/v1/health"}:
                self._send_json(200, {"status": "ok"})
                return
            if self.path == "/v1/models":
                self._send_json(200, gateway_models_payload())
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/v1/chat/completions", "/v1/images/generations"}:
                self._send_json(404, {"error": "not found"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                request_body = json.loads(raw_body.decode("utf-8") or "{}")
                if self.path == "/v1/chat/completions":
                    response = proxy_chat_completion(
                        request_body=request_body,
                        request_headers={k: v for k, v in self.headers.items()},
                        timeout=timeout,
                    )
                else:
                    response = proxy_image_generation(
                        request_body=request_body,
                        request_headers={k: v for k, v in self.headers.items()},
                        timeout=max(timeout, 90.0),
                    )
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(500, {"error": str(exc)})
                return
            except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
                self._send_json(502, {"error": f"Upstream request failed: {exc}"})
                return

            self.send_response(response.status_code)
            self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
            self.end_headers()
            self.wfile.write(response.content)

        def log_message(self, fmt: str, *args: object) -> None:
            logger.info("vizier_inference_gateway: " + fmt, *args)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), _GatewayHandler)
    logger.info(
        "Starting Vizier inference gateway on %s:%d -> %s / %s",
        host,
        port,
        default_openai_base_url(),
        default_ollama_base_url(),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
