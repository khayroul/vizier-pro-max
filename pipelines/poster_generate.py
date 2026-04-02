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
import mimetypes
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from adapter.llm_client import chat as llm_chat

logger = logging.getLogger(__name__)

_TEMPLATES_DIR: Path = Path(__file__).parent.parent / "templates" / "visual"
_OUTPUT_DIR: Path = Path(__file__).parent.parent / "output" / "posters"

_SLOT_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_META_PATTERN = re.compile(r'<meta\s+name="reactor-(\w+)"\s+content="([^"]+)"')
_HEX_PATTERN = re.compile(
    r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
)


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
    template_name: str = ""
    image_mode: str = ""
    output_path: str = ""
    brand_name: str = ""
    logo_mark: str = ""
    brand_css: dict[str, str] | None = None
    client_id: str = ""
    style_reference: str = ""
    reference_image_path: str = ""
    palette: dict[str, str] | None = None
    fonts: dict[str, str] | None = None


@dataclass(frozen=True)
class PosterResult:
    """Immutable result of poster generation."""

    poster_path: str
    hero_path: str
    template_used: str
    width: int
    height: int
    image_mode: str
    brand_name: str = ""
    logo_mark: str = ""


@dataclass(frozen=True)
class ReferenceStyleGuidance:
    """Structured style guidance extracted from a sample poster/image."""

    style_hint: str = ""
    avoid_hint: str = ""
    template_name: str = ""


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


def _encode_image_as_data_uri(image_path: str) -> str:
    """Read an image file and return a base64 data URI."""
    path = Path(image_path)
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime_type};base64,{encoded}"


def _extract_json_object(text: str) -> dict[str, object] | None:
    """Parse a JSON object from model output, tolerating fenced code blocks."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _analyze_reference_image(
    reference_image_path: str,
    available_templates: list[str],
) -> ReferenceStyleGuidance:
    """Use a vision-capable LLM to summarize a reference poster/image."""
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze design reference images for poster generation. "
                    "Return ONLY valid JSON with keys "
                    '{"style_hint":"...","avoid_hint":"...","template_name":"..."}. '
                    "style_hint should be a short art-direction summary. "
                    "avoid_hint should list what not to imitate. "
                    "template_name must be one of the provided template names or an empty string."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Study this reference image and summarize the reusable visual direction "
                            "for a new poster without copying exact text, logo, or trade dress. "
                            f"Available template names: {', '.join(available_templates)}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _encode_image_as_data_uri(reference_image_path),
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        max_tokens=300,
        timeout=45.0,
        strip_preamble=True,
    )
    if not result:
        return ReferenceStyleGuidance()

    payload = _extract_json_object(result)
    if payload is None:
        return ReferenceStyleGuidance()

    template_name = str(payload.get("template_name", "")).strip()
    if template_name and template_name not in available_templates:
        template_name = ""

    return ReferenceStyleGuidance(
        style_hint=str(payload.get("style_hint", "")).strip(),
        avoid_hint=str(payload.get("avoid_hint", "")).strip(),
        template_name=template_name,
    )


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB tuple to a hex color string."""
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Approximate luminance from RGB values."""
    red, green, blue = rgb
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


def _saturation(rgb: tuple[int, int, int]) -> float:
    """Approximate saturation from RGB values."""
    red, green, blue = [channel / 255.0 for channel in rgb]
    return max(red, green, blue) - min(red, green, blue)


def _extract_reference_brand_css(reference_image_path: str) -> dict[str, str]:
    """Derive CSS variables from the dominant colors of a reference image."""
    from PIL import Image

    image = Image.open(reference_image_path).convert("RGB")
    image.thumbnail((96, 96))
    quantized = image.quantize(colors=5)
    palette = quantized.getpalette() or []
    color_counts = quantized.getcolors() or []

    if not color_counts:
        return {
            "--bg-color": "#111111",
            "--accent-color": "#D1A054",
            "--font-headline": "Georgia",
            "--font-body": "Inter",
            "--font-headline-weight": "700",
            "--font-body-weight": "400",
            "--text-color": "#ffffff",
            "--text-muted": "rgba(255, 255, 255, 0.72)",
            "--color-accent": "#D1A054",
            "--color-accent-end": "#F5F5F5",
            "--color-accent-glow": "#D1A054",
            "--color-bg": "#111111",
            "--color-text": "#ffffff",
            "--font-heading": "Georgia",
            "--font-weight-heading": "700",
            "--font-weight-body": "400",
            "--letter-spacing-heading": "-0.02em",
            "--letter-spacing-body": "0em",
            "--line-height-heading": "1.1",
            "--line-height-body": "1.5",
        }

    swatches: list[tuple[int, tuple[int, int, int]]] = []
    for count, index in color_counts:
        rgb = tuple(palette[index * 3:index * 3 + 3])
        if len(rgb) == 3:
            swatches.append((count, rgb))  # type: ignore[arg-type]

    dominant_rgb = max(swatches, key=lambda item: item[0])[1]
    darkest_rgb = min(swatches, key=lambda item: _relative_luminance(item[1]))[1]
    lightest_rgb = max(swatches, key=lambda item: _relative_luminance(item[1]))[1]
    accent_rgb = max(swatches, key=lambda item: (_saturation(item[1]), item[0]))[1]

    background_rgb = darkest_rgb if _relative_luminance(darkest_rgb) < 0.55 else dominant_rgb
    text_hex = "#ffffff" if _relative_luminance(background_rgb) < 0.55 else "#111111"

    return {
        "--bg-color": _rgb_to_hex(background_rgb),
        "--accent-color": _rgb_to_hex(accent_rgb),
        "--font-headline": "Georgia",
        "--font-body": "Inter",
        "--font-headline-weight": "700",
        "--font-body-weight": "400",
        "--text-color": text_hex,
        "--text-muted": "rgba(255, 255, 255, 0.72)" if text_hex == "#ffffff" else "rgba(17, 17, 17, 0.72)",
        "--color-accent": _rgb_to_hex(accent_rgb),
        "--color-accent-end": _rgb_to_hex(lightest_rgb),
        "--color-accent-glow": _rgb_to_hex(accent_rgb),
        "--color-bg": _rgb_to_hex(background_rgb),
        "--color-text": text_hex,
        "--font-heading": "Georgia",
        "--font-weight-heading": "700",
        "--font-weight-body": "400",
        "--letter-spacing-heading": "-0.02em",
        "--letter-spacing-body": "0em",
        "--line-height-heading": "1.1",
        "--line-height-body": "1.5",
    }


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


def _validate_palette(palette: dict[str, str]) -> None:
    """Validate all palette values are valid hex colors."""
    for key in ("primary", "secondary", "accent", "background", "text"):
        value = palette.get(key, "")
        if not _HEX_PATTERN.match(value):
            msg = f"Invalid hex color for palette.{key}: {value!r}"
            raise ValueError(msg)


def _build_design_css(palette: dict[str, str], fonts: dict[str, str]) -> str:
    """Build CSS custom properties block from palette and font selections."""
    return (
        "<style>\n"
        ":root {\n"
        f"  --color-accent: {palette['primary']};\n"
        f"  --color-accent-end: {palette['secondary']};\n"
        f"  --color-accent-glow: {palette['accent']};\n"
        f"  --color-bg: {palette['background']};\n"
        f"  --color-text: {palette['text']};\n"
        f"  --font-heading: '{fonts['heading_font']}';\n"
        f"  --font-body: '{fonts['body_font']}';\n"
        f"  --font-weight-heading: {fonts['heading_weight']};\n"
        f"  --font-weight-body: {fonts['body_weight']};\n"
        f"  --letter-spacing-heading: {fonts['letter_spacing_heading']};\n"
        f"  --letter-spacing-body: {fonts['letter_spacing_body']};\n"
        f"  --line-height-heading: {fonts['line_height_heading']};\n"
        f"  --line-height-body: {fonts['line_height_body']};\n"
        "}\n"
        "</style>"
    )


def _build_font_link(fonts: dict[str, str]) -> str:
    """Build Google Fonts <link> tag for the selected font pairing.

    Loads heading weight, body weight, AND weight 600 for CTA button text.
    """
    heading = fonts["heading_font"].replace(" ", "+")
    body = fonts["body_font"].replace(" ", "+")
    hw = fonts["heading_weight"]
    bw = fonts["body_weight"]
    body_weights = sorted(set([bw, "600"]))
    body_wght = ";".join(body_weights)
    return (
        f'<link href="https://fonts.googleapis.com/css2?'
        f"family={heading}:wght@{hw}&"
        f'family={body}:wght@{body_wght}&display=swap" rel="stylesheet">'
    )


def _inject_design(html: str, palette: dict[str, str], fonts: dict[str, str]) -> str:
    """Inject design CSS and font link into HTML before </head>."""
    _validate_palette(palette)
    design_css = _build_design_css(palette, fonts)
    font_link = _build_font_link(fonts)
    return html.replace("</head>", f"{design_css}\n{font_link}\n</head>")


def _inject_brand_css(html: str, brand_css: dict[str, str]) -> str:
    """Inject CSS custom property overrides into HTML before </head>."""
    if not brand_css:
        return html
    declarations = "\n".join(f"    {key}: {value};" for key, value in brand_css.items())
    css_block = f"\n<style>\n  :root {{\n{declarations}\n  }}\n</style>\n"
    return html.replace("</head>", f"{css_block}</head>")


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
    brand_css: dict[str, str] | None = None,
    palette: dict[str, str] | None = None,
    fonts: dict[str, str] | None = None,
) -> str:
    """Inject content into template and render via Playwright."""
    html_source = Path(template.path).read_text(encoding="utf-8")

    # Inject design CSS BEFORE slot replacement to avoid {{regex}} conflicts
    if palette is not None and fonts is not None:
        html_source = _inject_design(html_source, palette, fonts)

    injected_html = _inject_slots(html_source, content)
    if brand_css is not None:
        injected_html = _inject_brand_css(injected_html, brand_css)

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
    template_name: str = "",
    image_mode: str = "",
    output_path: str = "",
    brand_name: str = "",
    logo_mark: str = "",
    brand_css: dict[str, str] | None = None,
    client_id: str = "",
    style_reference: str = "",
    reference_image_path: str = "",
    palette: dict[str, str] | None = None,
    fonts: dict[str, str] | None = None,
) -> dict[str, str | int]:
    """Generate a two-layer poster: AI background + HTML text overlay.

    Args:
        headline: Poster headline text (max ~8 words recommended).
        body: Poster body text (max ~220 chars recommended).
        cta: Call-to-action button text.
        image_prompt: Prompt for AI background generation. If empty,
            a default prompt is built from headline + body.
        template_name: HTML template to use. Falls back to client default or
            social-post.
        image_mode: Image generation provider — 'openai' or 'falai'.
        output_path: Where to save the final poster PNG. Auto-generated
            if empty.
        brand_name: Optional brand label injected into templates that support it.
        logo_mark: Optional short brand mark injected into templates that
            support it.
        brand_css: Optional CSS custom property overrides injected into the
            template.
        client_id: Optional client configuration ID for auto-theming.
        style_reference: Optional shared style preset such as ``"zus-coffee"``
            or ``"aesop"`` used to steer mood, template, and theming.
        reference_image_path: Optional local path to a sample poster/image used
            as direct visual inspiration.
        palette: Color palette dict with primary, secondary, accent,
            background, text hex values.
        fonts: Font pairing dict with heading_font, body_font, weights,
            spacing, and line heights.

    Returns:
        Dict with poster_path, hero_path, template_used, width, height,
        and image_mode.
    """
    t0 = time.monotonic()

    if (palette is None) != (fonts is None):
        msg = "palette and fonts must be provided together"
        raise ValueError(msg)

    client = None
    effective_template_name = template_name
    effective_image_mode = image_mode
    effective_brand_name = brand_name
    effective_logo_mark = logo_mark
    effective_brand_css = dict(brand_css) if brand_css is not None else None
    client_style_hint = ""
    style_reference_hint = ""
    style_reference_avoid = ""
    effective_style_reference = style_reference.strip()
    effective_reference_image_path = reference_image_path.strip()
    reference_image_hint = ""
    reference_image_avoid = ""

    if client_id:
        from config.client_loader import brand_to_css_vars, load_client

        client = load_client(client_id)
        if client is not None:
            client_style_hint = client.defaults.style_hint
            if not effective_image_mode:
                effective_image_mode = client.defaults.image_mode
            if not effective_logo_mark:
                effective_logo_mark = client.brand.logo_mark
            if not effective_brand_name:
                effective_brand_name = client.client_name
            if effective_brand_css is None:
                effective_brand_css = brand_to_css_vars(client.brand)
            if not effective_style_reference:
                effective_style_reference = client.defaults.style_reference.strip()

    if effective_style_reference:
        from config.client_loader import (
            load_style_reference,
            style_reference_to_css_vars,
        )

        style_ref = load_style_reference(effective_style_reference)
        if style_ref is None:
            msg = f"Unknown style_reference: {effective_style_reference}"
            raise ValueError(msg)
        style_reference_hint = style_ref.style_hint
        style_reference_avoid = style_ref.avoid_hint
        if not template_name and style_ref.template_name:
            effective_template_name = style_ref.template_name
        if effective_brand_css is None:
            effective_brand_css = style_reference_to_css_vars(style_ref)

    if effective_reference_image_path:
        reference_path = Path(effective_reference_image_path)
        if not reference_path.exists():
            msg = f"Reference image not found: {effective_reference_image_path}"
            raise FileNotFoundError(msg)

        available_templates = [template.name for template in list_templates()]
        reference_guidance = _analyze_reference_image(
            effective_reference_image_path,
            available_templates,
        )
        reference_image_hint = reference_guidance.style_hint
        reference_image_avoid = reference_guidance.avoid_hint
        if not template_name and reference_guidance.template_name:
            effective_template_name = reference_guidance.template_name
        if brand_css is None and palette is None and fonts is None:
            effective_brand_css = _extract_reference_brand_css(
                effective_reference_image_path
            )

    if (
        client is not None
        and not template_name
        and not style_reference.strip()
        and not effective_reference_image_path
    ):
        effective_template_name = client.defaults.template_name

    if not effective_template_name:
        effective_template_name = "social-post"
    if not effective_image_mode:
        effective_image_mode = "openai"
    if palette is None and fonts is None and effective_brand_css is None:
        msg = "palette/fonts or brand_css/client_id are required"
        raise ValueError(msg)

    # Resolve template
    template = _resolve_template(effective_template_name)

    # Build output paths
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = _OUTPUT_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    hero_path = str(out_dir / "hero.png")
    poster_path = output_path or str(out_dir / "poster.png")

    # Layer 1: Generate AI background
    prompt_prefix_parts = [
        part
        for part in (
            reference_image_hint,
            style_reference_hint,
            client_style_hint,
        )
        if part
    ]
    prompt_prefix = ". ".join(prompt_prefix_parts)
    if prompt_prefix:
        prompt_prefix += ". "
    avoid_parts = [part for part in (reference_image_avoid, style_reference_avoid) if part]
    avoid_sentence = f"Avoid {'; '.join(avoid_parts)}. " if avoid_parts else ""
    reference_sentence = (
        "Use the provided reference image as inspiration only, not an exact copy. "
        if effective_reference_image_path
        else ""
    )
    effective_prompt = image_prompt or (
        f"{prompt_prefix}"
        f"{reference_sentence}"
        f"Create a premium visual background for a poster about: "
        f"{headline}. {body}. "
        "No text, no logos, no letters, clean composition, "
        "vibrant colors, social-media ready lighting, high quality. "
        f"{avoid_sentence}"
    ).strip()
    hero_file = _generate_hero(effective_prompt, hero_path, effective_image_mode)

    # Layer 2: Render template with text + hero as background
    image_uri = _to_data_uri(Path(hero_file))
    content = {
        "headline": headline,
        "body": body,
        "cta": cta,
        "image_url": image_uri,
        "brand_name": effective_brand_name,
        "logo_mark": effective_logo_mark,
    }
    _render_poster(
        template,
        content,
        poster_path,
        brand_css=effective_brand_css,
        palette=palette,
        fonts=fonts,
    )

    duration = time.monotonic() - t0
    logger.info("Poster generated in %.1fs: %s", duration, poster_path)

    result = PosterResult(
        poster_path=poster_path,
        hero_path=hero_file,
        template_used=template.name,
        width=template.width,
        height=template.height,
        image_mode=effective_image_mode,
        brand_name=effective_brand_name,
        logo_mark=effective_logo_mark,
    )
    return {k: v for k, v in asdict(result).items()}
