"""Quality tests for clone_converge pipeline improvements."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

import pytest


def test_llm_receives_image_not_path() -> None:
    """First iteration must send base64 image, not a file path string."""
    from pipelines.clone_converge import _build_vision_messages

    import struct
    import zlib

    def _make_tiny_png() -> bytes:
        raw = b"\x00\xff\x00\x00"
        compressed = zlib.compress(raw)
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)

        def chunk(ctype: bytes, data: bytes) -> bytes:
            import binascii
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", binascii.crc32(c) & 0xFFFFFFFF)

        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(_make_tiny_png())
        tmp_path = f.name

    try:
        messages = _build_vision_messages(
            target_image_path=tmp_path,
            iteration=1,
        )
        user_msg = next(m for m in messages if m["role"] == "user")
        content = user_msg["content"]
        assert isinstance(content, list), "Vision messages must use list content blocks"
        image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image_url"]
        assert len(image_blocks) >= 1, "Must include at least one image_url block"
        url = image_blocks[0]["image_url"]["url"]
        assert url.startswith("data:image/"), f"Expected data URI, got: {url[:50]}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_delta_feedback_is_natural_language() -> None:
    """Delta feedback must be actionable text, not raw numbers."""
    from pipelines.clone_converge import _delta_to_guidance
    from scripts.visual.calculate_delta import DeltaResult

    delta = DeltaResult(
        ssim_score=0.3,
        pixel_diff_pct=45.0,
        color_delta_e=30.0,
        layout_score=0.4,
        text_match_pct=60.0,
        composite_score=0.35,
    )
    guidance = _delta_to_guidance(delta)
    assert any(word in guidance.lower() for word in ["color", "layout", "text", "structure", "match"])
    assert "SSIM:" not in guidance
