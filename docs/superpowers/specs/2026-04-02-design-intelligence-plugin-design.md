# Design Intelligence Plugin — Spec

**Date:** 2026-04-02
**Status:** Draft
**Scope:** Hermes plugin that adds palette + typography search from UI UX Pro Max data, integrated into the poster generation pipeline.

## Problem

The poster pipeline (`pipelines/poster_generate.py` + `templates/visual/social-post.html`) produces high-quality output but is locked to a single visual identity: gold accents (#d4a853/#f0d48a), Playfair Display headings, Inter body text. Every poster looks the same regardless of content.

## Solution

A Hermes plugin that bundles UI UX Pro Max's design databases (161 palettes, 73 font pairings) with a BM25 search engine, exposing two tools the agent calls before `generate_poster` to select contextually appropriate colors and typography.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration type | Hermes plugin | Local data, no subprocess overhead, lifecycle hooks |
| Selection model | Agent-chosen (B) | LLM calls search tools, picks from results |
| Result count | Top 5 | Balanced variety without token bloat |
| Data strategy | Bundled CSVs (A) | Offline, no network dependency, static data |
| Template mode | Always dynamic (A) | Remove hardcoded styles, palette+font always from plugin |

## Plugin Structure

```
plugins/design_intelligence/
  __init__.py          # register() — two tools
  search_engine.py     # BM25 search over CSV databases
  data/
    palettes.csv       # 161 palettes (from UI UX Pro Max)
    fonts.csv          # 73 font pairings
```

Only `palettes.csv` and `fonts.csv` are bundled. The reasoning rules (161) and styles (67) CSVs are not needed — the agent doesn't need category-to-style mapping logic since it picks directly from search results.

## Tool Schemas

### search_palettes

```json
{
  "name": "search_palettes",
  "description": "Search the design palette database by mood, style, or content keywords. Returns top 5 matching color palettes with hex values and mood tags. Call this BEFORE generate_poster to select colors.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query — mood keywords, content description, or style terms. Examples: 'warm artistic evening jazz', 'corporate clean minimal', 'vibrant tropical summer'"
      }
    },
    "required": ["query"]
  }
}
```

**Returns** (JSON array, top 5):
```json
[
  {
    "name": "Sunset Warmth",
    "primary": "#E07A5F",
    "secondary": "#F2CC8F",
    "accent": "#81B29A",
    "background": "#3D405B",
    "text": "#F4F1DE",
    "mood": "warm, inviting, artistic",
    "score": 4.82
  }
]
```

### search_fonts

```json
{
  "name": "search_fonts",
  "description": "Search the typography database by style, mood, or use-case keywords. Returns top 5 font pairings with weight and spacing specs. Call this BEFORE generate_poster to select typography.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query — style terms, mood, or use-case. Examples: 'elegant creative musical', 'bold modern tech', 'clean professional corporate'"
      }
    },
    "required": ["query"]
  }
}
```

**Returns** (JSON array, top 5):
```json
[
  {
    "name": "Elegant Contrast",
    "heading_font": "Cormorant Garamond",
    "heading_weight": "700",
    "body_font": "Lato",
    "body_weight": "400",
    "letter_spacing_heading": "-0.5px",
    "letter_spacing_body": "0px",
    "line_height_heading": "1.1",
    "line_height_body": "1.6",
    "mood": "elegant, refined, sophisticated",
    "score": 4.65
  }
]
```

## Search Engine

### BM25 Implementation

Ported from UI UX Pro Max's `design_system.py`, simplified:

- **Index:** Built once at plugin registration from CSV rows
- **Ranking:** BM25 with k1=1.5, b=0.75 (standard values)
- **Dependencies:** stdlib only (`csv`, `math`, `re`)
- **Memory:** ~200KB for all data loaded — negligible
- **Empty results:** If all BM25 scores are 0 (no term overlap), return the first 5 rows unsorted as a fallback. The agent always gets something to pick from.

```python
class BM25Index:
    def __init__(self, documents: list[dict[str, str]], fields: list[str]) -> None: ...
    def search(self, query: str, top_k: int = 5) -> list[dict]: ...
```

Each CSV row becomes a document. The `search()` method tokenizes the query, scores each document, and returns the top-k results with score attached.

### Expected CSV Column Headers

**palettes.csv** — fields searched: `name`, `mood`, `tags`
| Column | Purpose | Example |
|--------|---------|---------|
| `name` | Palette name | "Sunset Warmth" |
| `primary` | Primary accent hex | "#E07A5F" |
| `secondary` | Secondary accent hex | "#F2CC8F" |
| `accent` | Highlight/glow hex | "#81B29A" |
| `background` | Background hex | "#3D405B" |
| `text` | Text color hex | "#F4F1DE" |
| `mood` | Mood/style keywords | "warm, inviting, artistic" |
| `tags` | Category tags | "sunset, earthy, creative" |

**fonts.csv** — fields searched: `name`, `mood`, `tags`
| Column | Purpose | Example |
|--------|---------|---------|
| `name` | Pairing name | "Elegant Contrast" |
| `heading_font` | Heading typeface | "Cormorant Garamond" |
| `heading_weight` | Heading weight | "700" |
| `body_font` | Body typeface | "Lato" |
| `body_weight` | Body weight | "400" |
| `letter_spacing_heading` | Heading spacing | "-0.5px" |
| `letter_spacing_body` | Body spacing | "0px" |
| `line_height_heading` | Heading line height | "1.1" |
| `line_height_body` | Body line height | "1.6" |
| `mood` | Mood/style keywords | "elegant, refined, sophisticated" |
| `tags` | Category tags | "serif, luxury, editorial" |

All fonts in `fonts.csv` must be available on Google Fonts. During data bundling, verify each font exists at `fonts.google.com`. System-only or paid fonts are excluded from the CSV.

## Pipeline Integration

### PosterRequest Changes

Add two new fields to the frozen dataclass:

```python
@dataclass(frozen=True)
class PosterRequest:
    headline: str
    body: str
    cta: str = "Learn More"
    image_prompt: str = ""
    template_name: str = "social-post"
    image_mode: str = "openai"
    output_path: str = ""
    palette: dict[str, str] | None = None
    fonts: dict[str, str] | None = None
```

Both are dicts (not JSON strings) for type safety. The tool handler deserializes the LLM's JSON objects before constructing the request. `None` is not a valid runtime state — the agent must always provide both — but `None` as default avoids breaking `run()` callers during migration. If `None` is passed, `run()` raises `ValueError("palette and fonts are required")`.

### poster_generate.py `run()` Changes

After resolving the template:

1. Validate that `palette` and `fonts` are provided (raise `ValueError` if `None`)
2. Validate palette hex values match `#[0-9a-fA-F]{3,8}` pattern
3. Build a `<style>` block with CSS custom properties
4. Build a Google Fonts `<link>` tag for the selected font pairing (includes CTA weight 600)
5. Inject both into the HTML via `</head>` insertion (NOT slot replacement — avoids curly-brace conflicts with CSS)

**CSS injection strategy:** Insert the `<style>` block and `<link>` tag immediately before the closing `</head>` tag using `html.replace('</head>', f'{design_css}\n{font_link}\n</head>')`. This avoids the `{{slot}}` regex which would corrupt CSS content containing curly braces.

```python
_HEX_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")


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
    heading = fonts['heading_font'].replace(' ', '+')
    body = fonts['body_font'].replace(' ', '+')
    hw = fonts['heading_weight']
    bw = fonts['body_weight']
    # Always load 600 for CTA button, plus the specified weights
    body_weights = sorted(set([bw, "600"]))
    body_wght = ";".join(body_weights)
    return (
        f'<link href="https://fonts.googleapis.com/css2?'
        f'family={heading}:wght@{hw}&'
        f'family={body}:wght@{body_wght}&display=swap" rel="stylesheet">'
    )


def _inject_design(html: str, palette: dict[str, str], fonts: dict[str, str]) -> str:
    """Inject design CSS and font link into HTML before </head>."""
    _validate_palette(palette)
    design_css = _build_design_css(palette, fonts)
    font_link = _build_font_link(fonts)
    return html.replace("</head>", f"{design_css}\n{font_link}\n</head>")
```

The `run()` function calls `_inject_design()` on the raw HTML **before** `_inject_slots()`, so the CSS content is never exposed to the `{{slot}}` regex.

### Template Changes (social-post.html)

Replace all hardcoded values with CSS custom properties:

| Before | After |
|--------|-------|
| `font-family: 'Playfair Display', serif` | `font-family: var(--font-heading), serif` |
| `font-weight: 900` | `font-weight: var(--font-weight-heading)` |
| `letter-spacing: -0.5px` | `letter-spacing: var(--letter-spacing-heading)` |
| `line-height: 1.08` | `line-height: var(--line-height-heading)` |
| `font-family: 'Inter', sans-serif` | `font-family: var(--font-body), sans-serif` |
| `font-weight: 400` | `font-weight: var(--font-weight-body)` |
| `line-height: 1.6` | `line-height: var(--line-height-body)` |
| `#d4a853` / `#f0d48a` | `var(--color-accent)` / `var(--color-accent-end)` |
| `rgba(212,168,83,0.4)` (glow) | `var(--color-accent-glow)` with opacity via `color-mix()` |
| `color: #0a0a0f` (CTA text) | `color: var(--color-bg)` |
| `rgba(10,10,15,...)` (overlay) | `var(--color-bg)` with matching opacity stops |
| `background: #0a0a0f` (canvas) | `background: var(--color-bg)` |

**Overlay gradient fix (H2):** The `bg-overlay` gradient uses `var(--color-bg)` at each opacity stop instead of hardcoded `rgba(10,10,15,...)`. This ensures that light palettes get a light overlay (preserving readability by darkening/lightening toward the palette's background color):

```css
.bg-overlay {
  background: linear-gradient(
    178deg,
    color-mix(in srgb, var(--color-bg) 5%, transparent) 0%,
    color-mix(in srgb, var(--color-bg) 12%, transparent) 25%,
    color-mix(in srgb, var(--color-bg) 40%, transparent) 50%,
    color-mix(in srgb, var(--color-bg) 78%, transparent) 70%,
    color-mix(in srgb, var(--color-bg) 94%, transparent) 88%,
    color-mix(in srgb, var(--color-bg) 97%, transparent) 100%
  );
}
```

The hardcoded Google Fonts `<link>` tag is removed from the template. It's injected dynamically by the pipeline via `_inject_design()`.

The reactor-slots meta tag is **unchanged** — design injection uses `</head>` insertion, not slot replacement.

### poster_tool.py Changes

**Schema:** Add `palette` and `fonts` to `GENERATE_POSTER_SCHEMA`:

```json
{
  "palette": {
    "type": "object",
    "description": "Color palette from search_palettes result. Pass only the color fields (primary, secondary, accent, background, text) — drop name, mood, and score.",
    "properties": {
      "primary": { "type": "string" },
      "secondary": { "type": "string" },
      "accent": { "type": "string" },
      "background": { "type": "string" },
      "text": { "type": "string" }
    },
    "required": ["primary", "secondary", "accent", "background", "text"]
  },
  "fonts": {
    "type": "object",
    "description": "Font pairing from search_fonts result. Pass only the font fields — drop name, mood, and score.",
    "properties": {
      "heading_font": { "type": "string" },
      "heading_weight": { "type": "string" },
      "body_font": { "type": "string" },
      "body_weight": { "type": "string" },
      "letter_spacing_heading": { "type": "string" },
      "letter_spacing_body": { "type": "string" },
      "line_height_heading": { "type": "string" },
      "line_height_body": { "type": "string" }
    },
    "required": ["heading_font", "heading_weight", "body_font", "body_weight",
                  "letter_spacing_heading", "letter_spacing_body",
                  "line_height_heading", "line_height_body"]
  }
}
```

Both `palette` and `fonts` are required fields on `generate_poster`.

**Handler:** The `_handle_generate_poster` function must extract and pass the new fields:

```python
def _handle_generate_poster(args: dict[str, Any], agent: Any) -> str:
    from pipelines.poster_generate import run

    headline = str(args.get("headline", ""))
    body = str(args.get("body", ""))
    if not headline or not body:
        return json.dumps({"error": "headline and body are required"})

    palette = args.get("palette")
    fonts = args.get("fonts")
    if not palette or not fonts:
        return json.dumps({"error": "palette and fonts are required"})

    try:
        result = run(
            headline=headline,
            body=body,
            cta=str(args.get("cta", "Learn More")),
            image_prompt=str(args.get("image_prompt", "")),
            template_name=str(args.get("template_name", "social-post")),
            image_mode=str(args.get("image_mode", "openai")),
            output_path=str(args.get("output_path", "")),
            palette=palette,
            fonts=fonts,
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.exception("generate_poster failed")
        return json.dumps({"error": str(exc)})
```

## Agent Workflow

```
User: "Make a poster for a jazz festival this Saturday"

Agent:
  1. search_palettes(query="jazz festival warm artistic evening music")
     → receives 5 palettes, picks "Sunset Warmth"
  2. search_fonts(query="elegant creative musical performance")
     → receives 5 pairings, picks "Cormorant Garamond + Lato"
  3. generate_poster(
       headline="Jazz Under the Stars",
       body="Live performances, local food, craft cocktails. Join us Saturday evening.",
       cta="Get Tickets",
       palette={"primary": "#E07A5F", "secondary": "#F2CC8F", ...},
       fonts={"heading_font": "Cormorant Garamond", "heading_weight": "700", ...}
     )
     → poster rendered with contextual colors + typography
```

## System Prompt Update

Replace the existing `system_prompt_extra` in `config/hermes.yaml` with the merged version (YAML does not merge duplicate keys — last one wins):

```yaml
system_prompt_extra: |
  When asked to create a poster, flyer, banner, or social media graphic:
  - FIRST call search_palettes with mood/content keywords to find a color palette.
  - THEN call search_fonts with style keywords to find a font pairing.
  - Pick the best match from each result set (drop name, mood, score — pass only color/font fields).
  - THEN call generate_poster with the selected palette and fonts.
  - NEVER use execute_code with PIL/Pillow.
  - After generating, send the poster_path file to the user.
```

## Files Changed

| File | Change |
|------|--------|
| `plugins/design_intelligence/__init__.py` | **New** — plugin registration, two tools |
| `plugins/design_intelligence/search_engine.py` | **New** — BM25 index + search |
| `plugins/design_intelligence/data/palettes.csv` | **New** — bundled from UI UX Pro Max |
| `plugins/design_intelligence/data/fonts.csv` | **New** — bundled from UI UX Pro Max |
| `plugins/poster_tool.py` | **Modified** — add palette/fonts to schema, make required |
| `pipelines/poster_generate.py` | **Modified** — accept palette/fonts, inject CSS vars + font link |
| `templates/visual/social-post.html` | **Modified** — replace hardcoded values with CSS custom properties |
| `config/hermes.yaml` | **Modified** — update system prompt to instruct design tool usage |

## Testing

| Test | What it verifies |
|------|-----------------|
| `tests/plugins/test_design_intelligence.py` | BM25 search returns relevant results, correct JSON shape, top-k limit |
| `tests/pipelines/test_poster_generate.py` | Updated tests for CSS var injection, font link injection, palette/fonts required |
| `tests/plugins/test_poster_tool.py` | Schema validation with palette/fonts, handler passes them through |

## Known Constraints

- **Playwright font loading:** The pipeline renders with `wait_until="networkidle"`, which waits for Google Fonts to load before screenshotting. If the network is unavailable, fonts fall back to the generic `serif`/`sans-serif` specified in the template CSS. This is acceptable — the poster still renders, just with system fonts.
- **`color-mix()` support:** The `color-mix(in srgb, ...)` CSS function used in the overlay gradient requires Chromium 111+. Playwright bundles its own Chromium (currently 120+), so this is not a concern for rendering. It would only matter if the template were opened in an older browser, which is not a use case.

## Out of Scope

- Print-specific rules (CMYK, bleed, DPI) — not in UI UX Pro Max data
- Layout/composition changes — template structure stays the same
- Additional templates — only `social-post` is updated
- UI reasoning rules or style database — only palettes and fonts are bundled
- Semantic search — BM25 term matching is sufficient for this data size
