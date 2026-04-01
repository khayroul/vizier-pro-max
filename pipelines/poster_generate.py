"""Two-layer poster generation — AI background + Playwright text overlay.

Ported from Vizier Ultimate's E1/E4 engine pattern:
  1. Generate hero background via OpenAI gpt-image-1 or fal.ai FLUX
  2. Render HTML template with text slots via Playwright
  3. The template composites the AI background as a CSS background-image

The template handles compositing natively — the hero image is injected as
a data URI into the {{image_url}} slot, and CSS gradient overlays ensure
text readability. No separate Pillow alpha-composite step needed.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATES_DIR: Path = Path(__file__).parent.parent / "templates" / "visual"
_OUTPUT_DIR: Path = Path(__file__).parent.parent / "output" / "posters"

_SLOT_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_META_PATTERN = re.compile(r'<meta\s+name="reactor-(\w+)"\s+content="([^"]+)"')


# ---------------------------------------------------------------------------
# Types (frozen dataclasses — immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplateConfig:
    """Parsed metadata from an HTML template file."""

    name: str
    path: str
    width: int
    height: int
    slots: list[str]


@dataclass(frozen=True)
class PosterRequest:
    """Immutable request to generate a poster."""

    headline: str
    body: str
    cta: str = "Learn More"
    image_prompt: str = ""
    template_name: str = "social-post"
    image_mode: str = "openai"
    output_path: str = ""


@dataclass(frozen=True)
class PosterResult:
    """Immutable result of poster generation."""

    poster_path: str
    hero_path: str
    template_used: str
    width: int
    height: int
    image_mode: str


# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------


def _parse_template(html_file: Path) -> TemplateConfig:
    """Parse reactor meta tags from an HTML template."""
    raw = html_file.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    for match in _META_PATTERN.finditer(raw):
        meta[match.group(1)] = match.group(2)

    width = int(meta.get("width", "1080"))
    height = int(meta.get("height", "1080"))
    slots_raw = meta.get("slots", "")
    slots = [s.strip() for s in slots_raw.split(",") if s.strip()]

    return TemplateConfig(
        name=html_file.stem,
        path=str(html_file),
        width=width,
        height=height,
        slots=slots,
    )


def _resolve_template(template_name: str) -> TemplateConfig:
    """Find a template by name in the templates directory."""
    html_file = _TEMPLATES_DIR / f"{template_name}.html"
    if not html_file.exists():
        available = [f.stem for f in _TEMPLATES_DIR.glob("*.html")]
        msg = (
            f"Template '{template_name}' not found in {_TEMPLATES_DIR}. "
            f"Available: {available}"
        )
        raise FileNotFoundError(msg)
    return _parse_template(html_file)


def list_templates() -> list[TemplateConfig]:
    """Return all available poster templates."""
    if not _TEMPLATES_DIR.exists():
        return []
    return [
        _parse_template(html_file)
        for html_file in sorted(_TEMPLATES_DIR.glob("*.html"))
    ]


# ---------------------------------------------------------------------------
# Layer 1: AI background generation
# ---------------------------------------------------------------------------


def _generate_hero_openai(prompt: str, output_path: str) -> str:
    """Generate hero image via OpenAI gpt-image-1."""
    import openai

    client = openai.OpenAI(max_retries=3)

    logger.info("Generating hero image via OpenAI: %s", prompt[:80])
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="medium",
        n=1,
    )

    if not response.data:
        msg = "OpenAI returned no image data"
        raise ValueError(msg)

    image_item = response.data[0]
    raw_b64 = image_item.b64_json
    if raw_b64:
        image_bytes = base64.b64decode(raw_b64)
    elif image_item.url:
        import httpx

        resp = httpx.get(image_item.url, timeout=30)
        resp.raise_for_status()
        image_bytes = resp.content
    else:
        msg = "OpenAI returned no image data (no b64_json or url)"
        raise ValueError(msg)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    logger.info("Hero image saved: %s (%d bytes)", output_path, len(image_bytes))
    return str(out)


def _generate_hero_falai(prompt: str, output_path: str) -> str:
    """Generate hero image via fal.ai FLUX."""
    from scripts.visual.generate_image import run as fal_run

    result = fal_run(prompt=prompt, output_path=output_path, width=1024, height=1024)
    return result["file_path"]


def _generate_hero(prompt: str, output_path: str, mode: str) -> str:
    """Route hero generation to the appropriate provider."""
    if mode == "openai":
        return _generate_hero_openai(prompt, output_path)
    if mode == "falai":
        return _generate_hero_falai(prompt, output_path)
    msg = f"Invalid image_mode: {mode!r}. Must be 'openai' or 'falai'"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Layer 2: Template rendering via Playwright
# ---------------------------------------------------------------------------


def _to_data_uri(image_path: Path) -> str:
    """Encode a local image file as a base64 data URI."""
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    suffix = image_path.suffix.lstrip(".").lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix, "image/png"
    )
    return f"data:{mime};base64,{payload}"


def _inject_slots(html: str, content: dict[str, str]) -> str:
    """Replace {{slot_name}} placeholders with content values."""
    return _SLOT_PATTERN.sub(
        lambda match: content.get(match.group(1), ""),
        html,
    )


def _screenshot(html: str, output_path: str, width: int, height: int) -> None:
    """Render HTML to PNG via Playwright headless Chromium."""
    from playwright.sync_api import sync_playwright

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_viewport_size({"width": width, "height": height})
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=output_path, full_page=False)
            logger.debug("Screenshot saved: %s", output_path)
        finally:
            browser.close()


def _render_poster(
    template: TemplateConfig,
    content: dict[str, str],
    output_path: str,
) -> str:
    """Inject content into template and render via Playwright."""
    html_source = Path(template.path).read_text(encoding="utf-8")
    injected_html = _inject_slots(html_source, content)

    logger.info(
        "Rendering poster: template=%s, output=%s, size=%dx%d",
        template.name,
        output_path,
        template.width,
        template.height,
    )

    _screenshot(injected_html, output_path, template.width, template.height)
    return output_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    *,
    headline: str,
    body: str,
    cta: str = "Learn More",
    image_prompt: str = "",
    template_name: str = "social-post",
    image_mode: str = "openai",
    output_path: str = "",
) -> dict[str, str | int]:
    """Generate a two-layer poster: AI background + HTML text overlay.

    Args:
        headline: Poster headline text (max ~8 words recommended).
        body: Poster body text (max ~220 chars recommended).
        cta: Call-to-action button text.
        image_prompt: Prompt for AI background generation. If empty,
            a default prompt is built from headline + body.
        template_name: HTML template to use (default: social-post).
        image_mode: Image generation provider — 'openai' or 'falai'.
        output_path: Where to save the final poster PNG. Auto-generated
            if empty.

    Returns:
        Dict with poster_path, hero_path, template_used, width, height,
        and image_mode.
    """
    t0 = time.monotonic()

    # Resolve template
    template = _resolve_template(template_name)

    # Build output paths
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = _OUTPUT_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    hero_path = str(out_dir / "hero.png")
    poster_path = output_path or str(out_dir / "poster.png")

    # Layer 1: Generate AI background
    effective_prompt = image_prompt or (
        f"Create a premium visual background for a poster about: "
        f"{headline}. {body}. "
        "No text, no logos, no letters, clean composition, "
        "vibrant colors, social-media ready lighting, high quality."
    )
    hero_file = _generate_hero(effective_prompt, hero_path, image_mode)

    # Layer 2: Render template with text + hero as background
    image_uri = _to_data_uri(Path(hero_file))
    content = {
        "headline": headline,
        "body": body,
        "cta": cta,
        "image_url": image_uri,
    }
    _render_poster(template, content, poster_path)

    duration = time.monotonic() - t0
    logger.info("Poster generated in %.1fs: %s", duration, poster_path)

    result = PosterResult(
        poster_path=poster_path,
        hero_path=hero_file,
        template_used=template.name,
        width=template.width,
        height=template.height,
        image_mode=image_mode,
    )
    return {k: v for k, v in asdict(result).items()}
