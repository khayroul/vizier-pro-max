"""fal.ai image generation wrapper via httpx."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

FAL_API_URL = "https://fal.run"
DEFAULT_MODEL = "fal-ai/flux/schnell"


def run(
    *,
    prompt: str,
    output_path: str,
    model: str | None = None,
    width: int = 1024,
    height: int = 1024,
) -> dict[str, str]:
    """Generate an image via fal.ai and save locally.

    Args:
        prompt: Text description of the image to generate.
        output_path: Local filesystem path where the image will be saved.
        model: fal.ai model ID to use. Defaults to fal-ai/flux/schnell.
        width: Image width in pixels. Defaults to 1024.
        height: Image height in pixels. Defaults to 1024.

    Returns:
        Dict with ``file_path`` (local path) and ``image_url`` (fal.ai URL).

    Raises:
        RuntimeError: If FAL_KEY environment variable is not set.
        httpx.HTTPStatusError: If the API request fails.
    """
    api_key = os.environ.get("FAL_KEY")
    if not api_key:
        msg = "FAL_KEY environment variable required for image generation"
        raise RuntimeError(msg)

    effective_model = model or DEFAULT_MODEL
    url = f"{FAL_API_URL}/{effective_model}"

    response = httpx.post(
        url,
        headers={"Authorization": f"Key {api_key}"},
        json={
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    image_url = data["images"][0]["url"]
    img_response = httpx.get(image_url, timeout=30)
    img_response.raise_for_status()

    Path(output_path).write_bytes(img_response.content)
    logger.info("Generated image saved to %s", output_path)
    return {"file_path": output_path, "image_url": image_url}
