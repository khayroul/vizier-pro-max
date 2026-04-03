"""fal.ai image generation wrapper via the Vizier gateway."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

import httpx
import structlog

from adapter.env_loader import ensure_env
from middleware.deliverable_context import build_gateway_headers

logger = structlog.get_logger(__name__)

DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:11436/v1"
DEFAULT_MODEL = "fal-ai/flux/schnell"


def run(
    *,
    prompt: str,
    output_path: str,
    model: str | None = None,
    width: int = 1024,
    height: int = 1024,
    gateway_headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Generate an image via fal.ai through the Vizier gateway and save locally.

    Args:
        prompt: Text description of the image to generate.
        output_path: Local filesystem path where the image will be saved.
        model: fal.ai model ID to use. Defaults to fal-ai/flux/schnell.
        width: Image width in pixels. Defaults to 1024.
        height: Image height in pixels. Defaults to 1024.
        gateway_headers: Optional Vizier headers to stamp on the gateway call.

    Returns:
        Dict with ``file_path`` (local path) and ``image_url`` (fal.ai URL).

    Raises:
        RuntimeError: If the gateway request fails.
    """
    ensure_env()

    effective_model = model or DEFAULT_MODEL
    if not re.match(r"^[a-zA-Z0-9_/-]+$", effective_model) or ".." in effective_model:
        msg = f"Invalid model ID: {effective_model!r}"
        raise ValueError(msg)
    gateway_base_url = os.environ.get("VIZIER_GATEWAY_BASE_URL", DEFAULT_GATEWAY_BASE_URL).rstrip("/")
    headers = build_gateway_headers(source="pipeline", modality="image_generation")
    if gateway_headers:
        headers.update({str(key): str(value) for key, value in gateway_headers.items()})
    headers.setdefault("x-vizier-source", "pipeline")
    headers.setdefault("x-vizier-modality", "image_generation")

    response = httpx.post(
        f"{gateway_base_url}/images/generations",
        headers=headers,
        json={
            "prompt": prompt,
            "model": effective_model,
            "size": f"{width}x{height}",
            "image_size": {"width": width, "height": height},
        },
        timeout=60,
    )
    if response.status_code != 200:
        msg = f"Vizier gateway image generation failed with status {response.status_code}: {response.text}"
        raise RuntimeError(msg)
    data = response.json()

    images = data.get("images") or data.get("data") or []
    image_url = images[0]["url"]
    img_response = httpx.get(image_url, timeout=30)
    img_response.raise_for_status()

    Path(output_path).write_bytes(img_response.content)
    logger.info("Generated image saved to %s", output_path)
    return {"file_path": output_path, "image_url": image_url}
