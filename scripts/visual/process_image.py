"""Pillow image manipulation wrapper."""
from __future__ import annotations

import logging

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

_OPERATIONS = {"resize", "crop", "rotate", "watermark", "composite"}


def run(
    *,
    input_path: str,
    output_path: str,
    operation: str,
    width: int | None = None,
    height: int | None = None,
    angle: int | None = None,
    left: int | None = None,
    top: int | None = None,
    right: int | None = None,
    bottom: int | None = None,
    watermark_text: str | None = None,
    overlay_path: str | None = None,
) -> dict[str, str]:
    """Process an image with the specified operation.

    Args:
        input_path: Path to the source image file.
        output_path: Path where the processed image will be saved.
        operation: Operation to apply — resize, crop, rotate, watermark, or composite.
        width: Target width for resize.
        height: Target height for resize.
        angle: Rotation angle in degrees.
        left: Left coordinate for crop box.
        top: Top coordinate for crop box.
        right: Right coordinate for crop box.
        bottom: Bottom coordinate for crop box.
        watermark_text: Text to draw on the image for watermark.
        overlay_path: Path to overlay image for composite operation.

    Returns:
        Dict with key ``file_path`` pointing to the saved output image.

    Raises:
        ValueError: If an unknown operation is requested.
    """
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    img = Image.open(input_path)

    if operation == "resize":
        img = img.resize((width or img.width, height or img.height))
    elif operation == "crop":
        img = img.crop((left or 0, top or 0, right or img.width, bottom or img.height))
    elif operation == "rotate":
        img = img.rotate(angle or 0, expand=True)
    elif operation == "watermark":
        draw = ImageDraw.Draw(img)
        text = watermark_text or "DRAFT"
        draw.text((10, 10), text, fill=(255, 255, 255, 128))
    elif operation == "composite":
        if overlay_path:
            overlay = Image.open(overlay_path).resize(img.size)
            img = Image.alpha_composite(img.convert("RGBA"), overlay.convert("RGBA"))

    img.save(output_path)
    logger.info("Processed image saved to %s", output_path)
    return {"file_path": output_path}
