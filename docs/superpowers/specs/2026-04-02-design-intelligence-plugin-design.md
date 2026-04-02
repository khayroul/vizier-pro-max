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
- **Fields searched:** name, description, mood, tags (concatenated)
- **Ranking:** BM25 with k1=1.5, b=0.75 (standard values)
- **Dependencies:** stdlib only (`csv`, `math`, `re`)
- **Memory:** ~200KB for all data loaded — negligible

```python
class BM25Index:
    def __init__(self, documents: list[dict[str, str]], fields: list[str]) -> None: ...
    def search(self, query: str, top_k: int = 5) -> list[dict]: ...
```

Each CSV row becomes a document. The `search()` method tokenizes the query, scores each document, and returns the top-k results with score attached.

## Pipeline Integration

### PosterRequest Changes

Add two optional fields to the frozen dataclass:

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
    palette: str = ""    # JSON string of palette dict
    fonts: str = ""      # JSON string of fonts dict
```

Both are JSON strings (not dicts) to keep the dataclass simple and serializable. Parsed in the pipeline's `run()` function.

### poster_generate.py `run()` Changes

After resolving the template:

1. Parse `palette` and `fonts` JSON strings into dicts (empty string = no override = error, since always-dynamic)
2. Build a `<style>` block with CSS custom properties from the palette/font values
3. Build a Google Fonts `<link>` tag for the selected font pairing
4. Inject both into the HTML before slot replacement

```python
def _build_design_css(palette: dict[str, str], fonts: dict[str, str]) -> str:
    """Build CSS custom properties block from palette and font selections."""
    return f"""<style>
:root {{
  --color-accent: {palette['primary']};
  --color-accent-end: {palette['secondary']};
  --color-accent-glow: {palette['accent']};
  --color-bg: {palette['background']};
  --color-text: {palette['text']};
  --font-heading: '{fonts['heading_font']}';
  --font-body: '{fonts['body_font']}';
  --font-weight-heading: {fonts['heading_weight']};
  --font-weight-body: {fonts['body_weight']};
  --letter-spacing-heading: {fonts['letter_spacing_heading']};
  --letter-spacing-body: {fonts['letter_spacing_body']};
  --line-height-heading: {fonts['line_height_heading']};
  --line-height-body: {fonts['line_height_body']};
}}
</style>"""


def _build_font_link(fonts: dict[str, str]) -> str:
    """Build Google Fonts <link> tag for the selected font pairing."""
    heading = fonts['heading_font'].replace(' ', '+')
    body = fonts['body_font'].replace(' ', '+')
    hw = fonts['heading_weight']
    bw = fonts['body_weight']
    return (
        f'<link href="https://fonts.googleapis.com/css2?'
        f'family={heading}:wght@{hw}&'
        f'family={body}:wght@{bw}&display=swap" rel="stylesheet">'
    )
```

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
| `rgba(212,168,83,0.4)` (glow) | Derived from `var(--color-accent-glow)` |
| `color: #0a0a0f` (CTA text) | `color: var(--color-bg)` |

The hardcoded Google Fonts `<link>` tag is removed from the template. It's injected dynamically by the pipeline.

The reactor-slots meta tag updates to include the new design slots:
```html
<meta name="reactor-slots" content="headline,body,cta,image_url,design_css,font_link">
```

### poster_tool.py Schema Changes

Add `palette` and `fonts` to the tool schema:

```json
{
  "palette": {
    "type": "object",
    "description": "Color palette from search_palettes result. Must include: primary, secondary, accent, background, text.",
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
    "description": "Font pairing from search_fonts result. Must include heading/body font names, weights, spacing, and line heights.",
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

Both `palette` and `fonts` become required fields on `generate_poster` (since always-dynamic).

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

Update `config/hermes.yaml` to instruct the agent to use the design tools:

```yaml
system_prompt_extra: |
  When asked to create a poster, flyer, banner, or social media graphic:
  - FIRST call search_palettes with mood/content keywords to find a color palette.
  - THEN call search_fonts with style keywords to find a font pairing.
  - Pick the best match from each result set.
  - THEN call generate_poster with the selected palette and fonts.
  - NEVER use execute_code with PIL/Pillow.
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

## Out of Scope

- Print-specific rules (CMYK, bleed, DPI) — not in UI UX Pro Max data
- Layout/composition changes — template structure stays the same
- Additional templates — only `social-post` is updated
- UI reasoning rules or style database — only palettes and fonts are bundled
- Semantic search — BM25 term matching is sufficient for this data size
