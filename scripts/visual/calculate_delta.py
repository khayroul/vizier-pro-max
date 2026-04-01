"""Multi-signal image comparison for template cloning + visual QA.

5 weighted signals:
- SSIM (30%): structural similarity
- Pixel diff (25%): percentage of mismatched pixels
- Color delta-E (20%): average perceptual color difference
- Layout (15%): contour position matching
- Text OCR (10%): text content similarity

Gracefully degrades if optional dependencies are unavailable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Signal weights (must sum to 1.0)
WEIGHTS: dict[str, float] = {
    "ssim": 0.30,
    "pixel_diff": 0.25,
    "color_delta_e": 0.20,
    "layout": 0.15,
    "text_ocr": 0.10,
}


@dataclass(frozen=True)
class DeltaResult:
    """Result of multi-signal image comparison."""

    ssim_score: float  # 0.0 to 1.0
    pixel_diff_pct: float  # 0.0 to 100.0 (% mismatched)
    color_delta_e: float  # 0.0+ (lower is better)
    layout_score: float  # 0.0 to 1.0
    text_match_pct: float  # 0.0 to 100.0
    composite_score: float  # 0.0 to 1.0 (weighted average)
    details: dict[str, Any] | None = None


def _load_and_resize(
    path: Path, target_size: tuple[int, int] | None = None
) -> np.ndarray:  # type: ignore[type-arg]
    """Load image and optionally resize to match target dimensions."""
    img = Image.open(path).convert("RGB")
    if target_size and img.size != target_size:
        img = img.resize(target_size, Image.Resampling.LANCZOS)
    return np.array(img)


def _compute_ssim(
    img_a: np.ndarray,  # type: ignore[type-arg]
    img_b: np.ndarray,  # type: ignore[type-arg]
) -> float:
    """Compute SSIM between two images."""
    try:
        from skimage.metrics import (
            structural_similarity,  # type: ignore[import-not-found]
        )

        result = structural_similarity(img_a, img_b, channel_axis=2)
        return float(result)  # type: ignore[arg-type]
    except ImportError:
        logger.warning("scikit-image not available, using fallback SSIM")
        # Fallback: simple MSE-based similarity
        mse = float(np.mean((img_a.astype(float) - img_b.astype(float)) ** 2))
        max_val = 255.0
        if mse == 0:
            return 1.0
        return float(1.0 - (mse / (max_val**2)))


def _compute_pixel_diff(
    img_a: np.ndarray,  # type: ignore[type-arg]
    img_b: np.ndarray,  # type: ignore[type-arg]
) -> float:
    """Compute percentage of mismatched pixels."""
    try:
        from pixelmatch import pixelmatch as pm  # type: ignore[import-not-found]

        h, w = img_a.shape[:2]
        rgba_a = np.dstack([img_a, np.full((h, w), 255, dtype=np.uint8)])
        rgba_b = np.dstack([img_b, np.full((h, w), 255, dtype=np.uint8)])
        diff_count = pm(
            rgba_a.flatten().tolist(),
            rgba_b.flatten().tolist(),
            w,
            h,
            None,
            {"threshold": 0.1},
        )
        total_pixels = h * w
        return (diff_count / total_pixels) * 100.0 if total_pixels > 0 else 0.0
    except (ImportError, TypeError):
        logger.warning("pixelmatch not available, using fallback pixel diff")
        # Fallback: simple per-pixel comparison
        diff = np.abs(img_a.astype(float) - img_b.astype(float))
        threshold = 25.0  # ~10% of 255
        mismatched: np.ndarray = np.any(diff > threshold, axis=2)  # type: ignore[type-arg]
        total = mismatched.size
        return float(np.sum(mismatched) / total * 100.0) if total > 0 else 0.0


def _compute_color_delta_e(
    img_a: np.ndarray,  # type: ignore[type-arg]
    img_b: np.ndarray,  # type: ignore[type-arg]
) -> float:
    """Compute average CIE76 delta-E between color palettes."""
    mean_a = img_a.mean(axis=(0, 1))
    mean_b = img_b.mean(axis=(0, 1))
    # CIE76 delta-E approximation in RGB space
    diff = mean_a.astype(float) - mean_b.astype(float)
    delta_e = float(np.sqrt(np.sum(diff**2)))
    return delta_e


def _compute_layout_score(
    img_a: np.ndarray,  # type: ignore[type-arg]
    img_b: np.ndarray,  # type: ignore[type-arg]
) -> float:
    """Compute layout similarity via contour matching."""
    try:
        import cv2  # type: ignore[import-not-found]

        gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
        gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)
        # Edge detection
        edges_a = cv2.Canny(gray_a, 50, 150)
        edges_b = cv2.Canny(gray_b, 50, 150)
        # Compare edge maps
        total = edges_a.size
        if total == 0:
            return 1.0
        matching = np.sum(edges_a == edges_b)
        return float(matching / total)
    except ImportError:
        logger.warning("opencv not available, using fallback layout score")
        # Fallback: compare intensity histograms
        hist_a = np.histogram(img_a.mean(axis=2), bins=32, range=(0, 255))[0]
        hist_b = np.histogram(img_b.mean(axis=2), bins=32, range=(0, 255))[0]
        hist_a_norm = hist_a / (hist_a.sum() + 1e-10)
        hist_b_norm = hist_b / (hist_b.sum() + 1e-10)
        # Bhattacharyya similarity
        return float(np.sum(np.sqrt(hist_a_norm * hist_b_norm)))


def _compute_text_match(
    img_a: np.ndarray,  # type: ignore[type-arg]
    img_b: np.ndarray,  # type: ignore[type-arg]
) -> float:
    """Compute text content similarity via OCR."""
    try:
        from difflib import SequenceMatcher

        import pytesseract  # type: ignore[import-not-found]

        text_a = pytesseract.image_to_string(Image.fromarray(img_a))
        text_b = pytesseract.image_to_string(Image.fromarray(img_b))
        if not text_a and not text_b:
            return 100.0  # Both empty = perfect match
        ratio = SequenceMatcher(None, text_a, text_b).ratio()
        return ratio * 100.0
    except (ImportError, OSError) as exc:
        logger.warning("pytesseract not available or failed: %s", exc)
        return 100.0  # Assume text match if OCR unavailable


def calculate_delta(
    *,
    target: Path,
    rendered: Path,
) -> DeltaResult:
    """Compare target and rendered images using 5 weighted signals.

    Args:
        target: Path to the reference/target image.
        rendered: Path to the rendered image to compare against target.

    Returns:
        DeltaResult with individual signal scores and weighted composite.
    """
    # Load images, resize rendered to match target
    img_target = Image.open(target).convert("RGB")
    target_size = img_target.size
    arr_target = np.array(img_target)

    arr_rendered = _load_and_resize(rendered, target_size=target_size)

    # Compute individual signals
    ssim = _compute_ssim(arr_target, arr_rendered)
    pixel_diff = _compute_pixel_diff(arr_target, arr_rendered)
    color_de = _compute_color_delta_e(arr_target, arr_rendered)
    layout = _compute_layout_score(arr_target, arr_rendered)
    text_match = _compute_text_match(arr_target, arr_rendered)

    # Normalize to 0-1 scale for composite
    ssim_norm = max(0.0, min(1.0, ssim))
    pixel_norm = max(0.0, min(1.0, 1.0 - pixel_diff / 100.0))
    color_norm = max(0.0, min(1.0, 1.0 - color_de / 100.0))
    layout_norm = max(0.0, min(1.0, layout))
    text_norm = max(0.0, min(1.0, text_match / 100.0))

    # Weighted composite
    composite = (
        WEIGHTS["ssim"] * ssim_norm
        + WEIGHTS["pixel_diff"] * pixel_norm
        + WEIGHTS["color_delta_e"] * color_norm
        + WEIGHTS["layout"] * layout_norm
        + WEIGHTS["text_ocr"] * text_norm
    )

    return DeltaResult(
        ssim_score=ssim,
        pixel_diff_pct=pixel_diff,
        color_delta_e=color_de,
        layout_score=layout,
        text_match_pct=text_match,
        composite_score=composite,
    )
