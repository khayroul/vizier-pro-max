#!/usr/bin/env python3
"""Build normalized reference corpora from pinned raw upstream snapshots."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REFERENCES_ROOT = ROOT / "references"

_LIST_SPLIT_PATTERN = re.compile(r"\s*(?:,|\|)\s*")
_MULTISPACE_PATTERN = re.compile(r"\s+")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    collapsed = _NON_ALNUM_PATTERN.sub("-", lowered)
    return collapsed.strip("-")


def _clean_text(value: str) -> str:
    return _MULTISPACE_PATTERN.sub(" ", value.strip())


def _split_list(value: str) -> list[str]:
    if not value:
        return []
    pieces = [
        part.strip().lstrip("☐").strip()
        for part in _LIST_SPLIT_PATTERN.split(value)
    ]
    return [piece for piece in pieces if piece]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_dataset(
    path: Path,
    *,
    dataset_id: str,
    source_family: str,
    description: str,
    generated_from: list[str],
    items: list[dict[str, Any]],
) -> None:
    payload = {
        "dataset_id": dataset_id,
        "source_family": source_family,
        "description": description,
        "generated_from": generated_from,
        "record_count": len(items),
        "items": items,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _description_text(value: Any) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        for key in ("short", "long"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return _clean_text(text)
    return ""


def _schema_summary(schema: Any) -> str:
    if isinstance(schema, dict):
        if "enum" in schema:
            values = ", ".join(str(item) for item in schema["enum"])
            return f"enum({values})"
        if "ref" in schema:
            return f"ref({schema['ref']})"
        if "string" in schema:
            string_schema = schema["string"]
            if isinstance(string_schema, dict) and "completions" in string_schema:
                values = ", ".join(str(item) for item in string_schema["completions"])
                return f"string(completions: {values})"
            return "string"
        if "number" in schema:
            return "number"
        if "boolean" in schema:
            return "boolean"
        if "maybeArrayOf" in schema:
            return f"maybeArrayOf({_schema_summary(schema['maybeArrayOf'])})"
        if "arrayOf" in schema:
            return f"arrayOf({_schema_summary(schema['arrayOf'])})"
        if "object" in schema:
            properties = schema["object"].get("properties", {})
            keys = ", ".join(properties.keys())
            return f"object({keys})"
        if "anyOf" in schema:
            return " | ".join(_schema_summary(option) for option in schema["anyOf"])
    if isinstance(schema, str):
        return schema
    return "mixed"


def _camel_to_slug(value: str) -> str:
    step_one = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", value)
    step_two = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", step_one)
    return step_two.lower()


def _extract_ref_name(reference: str) -> str:
    return reference.rsplit("/", maxsplit=1)[-1]


def _normalize_ui_ux() -> None:
    family = "ui_ux_pro_max"
    raw_dir = REFERENCES_ROOT / family / "raw"
    normalized_dir = REFERENCES_ROOT / family / "normalized"

    styles_rows = _load_csv(raw_dir / "styles.csv")
    styles_items: list[dict[str, Any]] = []
    motif_items: list[dict[str, Any]] = []
    for row in styles_rows:
        style_id = _slugify(row["Style Category"])
        styles_items.append(
            {
                "id": style_id,
                "name": row["Style Category"],
                "type": row["Type"],
                "keywords": _split_list(row["Keywords"]),
                "best_for": _split_list(row["Best For"]),
                "avoid_for": _split_list(row["Do Not Use For"]),
                "light_mode": row["Light Mode ✓"],
                "dark_mode": row["Dark Mode ✓"],
                "performance": row["Performance"],
                "accessibility": row["Accessibility"],
                "mobile_friendly": row["Mobile-Friendly"],
                "conversion_focused": row["Conversion-Focused"],
                "framework_compatibility": _split_list(
                    row["Framework Compatibility"]
                ),
                "era_origin": row["Era/Origin"],
                "complexity": row["Complexity"],
                "source_row": int(row["No"]),
            }
        )
        motif_items.append(
            {
                "id": style_id,
                "style_name": row["Style Category"],
                "primary_colors": _split_list(row["Primary Colors"]),
                "secondary_colors": _split_list(row["Secondary Colors"]),
                "effects_animations": _split_list(row["Effects & Animation"]),
                "ai_prompt_keywords": _split_list(row["AI Prompt Keywords"]),
                "css_keywords": _split_list(row["CSS/Technical Keywords"]),
                "implementation_checklist": _split_list(
                    row["Implementation Checklist"]
                ),
                "design_system_variables": _split_list(
                    row["Design System Variables"]
                ),
            }
        )

    ux_rows = _load_csv(raw_dir / "ux-guidelines.csv")
    ux_items = [
        {
            "id": _slugify(f"{row['Category']}-{row['Issue']}-{row['Platform']}"),
            "category": row["Category"],
            "issue": row["Issue"],
            "platform": row["Platform"],
            "description": row["Description"],
            "recommended_practice": row["Do"],
            "avoid": row["Don't"],
            "code_example_good": row["Code Example Good"],
            "code_example_bad": row["Code Example Bad"],
            "severity": row["Severity"],
            "source_row": int(row["No"]),
        }
        for row in ux_rows
    ]

    landing_rows = _load_csv(raw_dir / "landing.csv")
    landing_items = [
        {
            "id": _slugify(row["Pattern Name"]),
            "pattern_name": row["Pattern Name"],
            "keywords": _split_list(row["Keywords"]),
            "section_order": _split_list(row["Section Order"]),
            "primary_cta_placement": row["Primary CTA Placement"],
            "color_strategy": row["Color Strategy"],
            "recommended_effects": _split_list(row["Recommended Effects"]),
            "conversion_optimization": row["Conversion Optimization"],
            "source_row": int(row["No"]),
        }
        for row in landing_rows
    ]

    chart_rows = _load_csv(raw_dir / "charts.csv")
    chart_items = [
        {
            "id": _slugify(row["Data Type"]),
            "data_type": row["Data Type"],
            "keywords": _split_list(row["Keywords"]),
            "best_chart_type": row["Best Chart Type"],
            "secondary_options": _split_list(row["Secondary Options"]),
            "when_to_use": row["When to Use"],
            "when_not_to_use": row["When NOT to Use"],
            "data_volume_threshold": row["Data Volume Threshold"],
            "color_guidance": row["Color Guidance"],
            "accessibility_grade": row["Accessibility Grade"],
            "accessibility_notes": row["Accessibility Notes"],
            "a11y_fallback": row["A11y Fallback"],
            "library_recommendation": _split_list(row["Library Recommendation"]),
            "interactive_level": row["Interactive Level"],
            "source_row": int(row["No"]),
        }
        for row in chart_rows
    ]

    typography_rows = _load_csv(raw_dir / "typography.csv")
    typography_items = [
        {
            "id": _slugify(row["Font Pairing Name"]),
            "pairing_name": row["Font Pairing Name"],
            "category": row["Category"],
            "heading_font": row["Heading Font"],
            "body_font": row["Body Font"],
            "mood_keywords": _split_list(row["Mood/Style Keywords"]),
            "best_for": _split_list(row["Best For"]),
            "google_fonts_url": row["Google Fonts URL"],
            "css_import": row["CSS Import"],
            "tailwind_config": row["Tailwind Config"],
            "notes": row["Notes"],
            "source_row": int(row["No"]),
        }
        for row in typography_rows
    ]

    color_rows = _load_csv(raw_dir / "colors.csv")
    color_items = [
        {
            "id": _slugify(row["Product Type"]),
            "product_type": row["Product Type"],
            "primary": row["Primary"],
            "on_primary": row["On Primary"],
            "secondary": row["Secondary"],
            "on_secondary": row["On Secondary"],
            "accent": row["Accent"],
            "on_accent": row["On Accent"],
            "background": row["Background"],
            "foreground": row["Foreground"],
            "card": row["Card"],
            "card_foreground": row["Card Foreground"],
            "muted": row["Muted"],
            "muted_foreground": row["Muted Foreground"],
            "border": row["Border"],
            "destructive": row["Destructive"],
            "on_destructive": row["On Destructive"],
            "ring": row["Ring"],
            "notes": row["Notes"],
            "source_row": int(row["No"]),
        }
        for row in color_rows
    ]

    _write_dataset(
        normalized_dir / "ui_styles.json",
        dataset_id="ui_styles",
        source_family=family,
        description="Structured UI style families from UI UX Pro Max.",
        generated_from=["references/ui_ux_pro_max/raw/styles.csv"],
        items=styles_items,
    )
    _write_dataset(
        normalized_dir / "visual_motifs.json",
        dataset_id="visual_motifs",
        source_family=family,
        description="Visual motif and implementation heuristics derived from UI UX Pro Max styles.",
        generated_from=["references/ui_ux_pro_max/raw/styles.csv"],
        items=motif_items,
    )
    _write_dataset(
        normalized_dir / "ux_guidelines.json",
        dataset_id="ux_guidelines",
        source_family=family,
        description="Actionable UX practices and anti-patterns from UI UX Pro Max.",
        generated_from=["references/ui_ux_pro_max/raw/ux-guidelines.csv"],
        items=ux_items,
    )
    _write_dataset(
        normalized_dir / "landing_patterns.json",
        dataset_id="landing_patterns",
        source_family=family,
        description="Layout and CTA patterns for marketing-style surfaces from UI UX Pro Max.",
        generated_from=["references/ui_ux_pro_max/raw/landing.csv"],
        items=landing_items,
    )
    _write_dataset(
        normalized_dir / "chart_usage_patterns.json",
        dataset_id="chart_usage_patterns",
        source_family=family,
        description="Chart-selection heuristics from UI UX Pro Max.",
        generated_from=["references/ui_ux_pro_max/raw/charts.csv"],
        items=chart_items,
    )
    _write_dataset(
        normalized_dir / "typography_pairings.json",
        dataset_id="typography_pairings",
        source_family=family,
        description="Font pairing references from UI UX Pro Max.",
        generated_from=["references/ui_ux_pro_max/raw/typography.csv"],
        items=typography_items,
    )
    _write_dataset(
        normalized_dir / "color_systems.json",
        dataset_id="color_systems",
        source_family=family,
        description="Product-type color systems from UI UX Pro Max.",
        generated_from=["references/ui_ux_pro_max/raw/colors.csv"],
        items=color_items,
    )


def _spec_marks(spec: dict[str, Any]) -> set[str]:
    marks: set[str] = set()
    mark = spec.get("mark")
    if isinstance(mark, str):
        marks.add(mark)
    elif isinstance(mark, dict) and isinstance(mark.get("type"), str):
        marks.add(mark["type"])

    if isinstance(spec.get("layer"), list):
        for item in spec["layer"]:
            marks.update(_spec_marks(item))
    if isinstance(spec.get("spec"), dict):
        marks.update(_spec_marks(spec["spec"]))
    for key in ("concat", "hconcat", "vconcat"):
        if isinstance(spec.get(key), list):
            for item in spec[key]:
                marks.update(_spec_marks(item))
    return marks


def _spec_channels(spec: dict[str, Any]) -> set[str]:
    channels: set[str] = set()
    encoding = spec.get("encoding")
    if isinstance(encoding, dict):
        channels.update(encoding.keys())

    if isinstance(spec.get("layer"), list):
        for item in spec["layer"]:
            channels.update(_spec_channels(item))
    if isinstance(spec.get("spec"), dict):
        channels.update(_spec_channels(spec["spec"]))
    for key in ("concat", "hconcat", "vconcat"):
        if isinstance(spec.get(key), list):
            for item in spec[key]:
                channels.update(_spec_channels(item))
    return channels


def _spec_compositions(spec: dict[str, Any]) -> set[str]:
    compositions: set[str] = set()
    for key in ("layer", "facet", "repeat", "concat", "hconcat", "vconcat"):
        if key in spec:
            compositions.add(key)
    if not compositions:
        compositions.add("unit")
    if isinstance(spec.get("layer"), list):
        for item in spec["layer"]:
            compositions.update(_spec_compositions(item))
    if isinstance(spec.get("spec"), dict):
        compositions.update(_spec_compositions(spec["spec"]))
    return compositions


def _spec_transforms(spec: dict[str, Any]) -> set[str]:
    transforms: set[str] = set()
    transform_list = spec.get("transform")
    if isinstance(transform_list, list):
        for item in transform_list:
            if not isinstance(item, dict):
                continue
            for key in item:
                transforms.add(key)
    if isinstance(spec.get("layer"), list):
        for item in spec["layer"]:
            transforms.update(_spec_transforms(item))
    if isinstance(spec.get("spec"), dict):
        transforms.update(_spec_transforms(spec["spec"]))
    return transforms


def _normalize_vega_lite() -> None:
    family = "vega_lite"
    raw_dir = REFERENCES_ROOT / family / "raw"
    normalized_dir = REFERENCES_ROOT / family / "normalized"

    schema = _load_json(raw_dir / "vega-lite-schema.json")
    definitions = schema["definitions"]

    mark_values = sorted(definitions["Mark"]["enum"])
    composite_refs = definitions["CompositeMark"]["anyOf"]
    composite_values = sorted(
        _camel_to_slug(_extract_ref_name(option["$ref"])) for option in composite_refs
    )
    encoding_channels = sorted(definitions["FacetedEncoding"]["properties"].keys())
    transform_ops = sorted(
        _camel_to_slug(name.removesuffix("Transform"))
        for name in definitions
        if name.endswith("Transform") and name != "Transform"
    )
    composition_ops = [
        "unit",
        "layer",
        "facet",
        "repeat",
        "concat",
        "hconcat",
        "vconcat",
    ]
    grammar_items = [
        {
            "id": "marks",
            "label": "Marks",
            "values": mark_values + composite_values,
        },
        {
            "id": "encoding_channels",
            "label": "Encoding Channels",
            "values": encoding_channels,
        },
        {
            "id": "transform_ops",
            "label": "Transform Operations",
            "values": transform_ops,
        },
        {
            "id": "composition_ops",
            "label": "Composition Operations",
            "values": composition_ops,
        },
    ]

    pattern_specs = [
        {
            "dataset_id": "bar",
            "title": "Categorical Comparison",
            "analytic_goal": "Compare ranked category magnitudes with a simple bar chart.",
            "family": "comparison",
            "when_to_use": "Discrete categories with one main metric and a need for quick ranking.",
            "avoid_when": "When the x-axis is temporal or when proportions are the primary story.",
            "accessibility_notes": "Prefer direct labels or accessible tooltips for category-value pairs.",
        },
        {
            "dataset_id": "line",
            "title": "Trend Over Time",
            "analytic_goal": "Track a continuous metric across time with a line chart.",
            "family": "trend",
            "when_to_use": "Time series with enough points to show movement or slope changes.",
            "avoid_when": "When categories are not ordered in time or there are too many overlapping series.",
            "accessibility_notes": "Use clear axis titles and point markers when the line is dense.",
        },
        {
            "dataset_id": "arc_pie",
            "title": "Part to Whole",
            "analytic_goal": "Show a small number of proportions with an arc/pie chart.",
            "family": "composition",
            "when_to_use": "A handful of categories where percentage share is more important than precision.",
            "avoid_when": "When there are many slices or subtle percentage differences.",
            "accessibility_notes": "Provide labels or a fallback table because color alone is weak.",
        },
        {
            "dataset_id": "rect_binned_heatmap",
            "title": "Binned Density Heatmap",
            "analytic_goal": "Reveal distribution density across two quantitative axes.",
            "family": "distribution",
            "when_to_use": "Large point clouds where raw scatter marks would overplot heavily.",
            "avoid_when": "When the audience needs exact point-level values instead of density patterns.",
            "accessibility_notes": "Pair the color scale with a legend and narrative explanation of density bands.",
        },
        {
            "dataset_id": "layer_line_errorband_ci",
            "title": "Trend With Uncertainty Band",
            "analytic_goal": "Combine a mean line with confidence intervals in one layered view.",
            "family": "uncertainty",
            "when_to_use": "Time trends where the uncertainty envelope is as important as the mean.",
            "avoid_when": "When the audience only needs a point estimate or the intervals are uninterpretable.",
            "accessibility_notes": "Use a sufficiently opaque band and explain what the interval means.",
        },
        {
            "dataset_id": "point_color_with_shape",
            "title": "Correlation With Group Encoding",
            "analytic_goal": "Show the relationship between two quantitative fields with grouped points.",
            "family": "relationship",
            "when_to_use": "Pairwise quantitative comparison with categorical grouping.",
            "avoid_when": "When there are too many points for overlap or no relationship to compare.",
            "accessibility_notes": "Use both color and shape so groups remain distinguishable.",
        },
        {
            "dataset_id": "trellis_barley",
            "title": "Small Multiples Comparison",
            "analytic_goal": "Use faceting to compare repeated measures across categories.",
            "family": "comparison",
            "when_to_use": "One repeated structure per site, region, or cohort needs side-by-side reading.",
            "avoid_when": "When there are too many facets or the repeated pattern is not comparable.",
            "accessibility_notes": "Keep facet counts manageable and titles descriptive.",
        },
        {
            "dataset_id": "repeat_splom",
            "title": "Scatterplot Matrix",
            "analytic_goal": "Inspect many pairwise quantitative relationships at once.",
            "family": "exploration",
            "when_to_use": "Several quantitative measures need broad exploratory comparison.",
            "avoid_when": "When the audience only needs one or two key relationships.",
            "accessibility_notes": "Highlight the most important pairs in narrative text for faster reading.",
        },
    ]

    pattern_items: list[dict[str, Any]] = []
    for pattern in pattern_specs:
        spec_path = raw_dir / "examples" / "specs" / f"{pattern['dataset_id']}.vl.json"
        spec = _load_json(spec_path)
        pattern_items.append(
            {
                "id": _slugify(pattern["dataset_id"]),
                "title": pattern["title"],
                "analytic_goal": pattern["analytic_goal"],
                "family": pattern["family"],
                "when_to_use": pattern["when_to_use"],
                "avoid_when": pattern["avoid_when"],
                "accessibility_notes": pattern["accessibility_notes"],
                "source_spec": f"references/vega_lite/raw/examples/specs/{spec_path.name}",
                "description": spec.get("description", ""),
                "marks": sorted(_spec_marks(spec)),
                "channels": sorted(_spec_channels(spec)),
                "transforms": sorted(_spec_transforms(spec)),
                "composition": sorted(_spec_compositions(spec)),
            }
        )

    _write_dataset(
        normalized_dir / "chart_grammar.json",
        dataset_id="chart_grammar",
        source_family=family,
        description="Core chart grammar families derived from the Vega-Lite schema.",
        generated_from=["references/vega_lite/raw/vega-lite-schema.json"],
        items=grammar_items,
    )
    _write_dataset(
        normalized_dir / "chart_patterns.json",
        dataset_id="chart_patterns",
        source_family=family,
        description="Curated analytic chart patterns anchored to pinned Vega-Lite example specs.",
        generated_from=[
            "references/vega_lite/raw/examples/specs/bar.vl.json",
            "references/vega_lite/raw/examples/specs/line.vl.json",
            "references/vega_lite/raw/examples/specs/arc_pie.vl.json",
            "references/vega_lite/raw/examples/specs/rect_binned_heatmap.vl.json",
            "references/vega_lite/raw/examples/specs/layer_line_errorband_ci.vl.json",
            "references/vega_lite/raw/examples/specs/point_color_with_shape.vl.json",
            "references/vega_lite/raw/examples/specs/trellis_barley.vl.json",
            "references/vega_lite/raw/examples/specs/repeat_splom.vl.json",
        ],
        items=pattern_items,
    )


def _normalize_quarto() -> None:
    family = "quarto"
    raw_dir = REFERENCES_ROOT / family / "raw"
    normalized_dir = REFERENCES_ROOT / family / "normalized"

    layout_rows = _load_yaml(
        raw_dir / "src" / "resources" / "schema" / "document-layout.yml"
    )
    layout_items = [
        {
            "id": _slugify(row["name"]),
            "option": row["name"],
            "formats": row.get("tags", {}).get("formats", []),
            "default": row.get("default"),
            "schema_summary": _schema_summary(row.get("schema")),
            "description": _description_text(row.get("description", "")),
        }
        for row in layout_rows
    ]

    figures_rows = _load_yaml(
        raw_dir / "src" / "resources" / "schema" / "document-figures.yml"
    )
    table_rows = _load_yaml(raw_dir / "src" / "resources" / "schema" / "cell-table.yml")
    table_figure_items = [
        {
            "id": _slugify(row["name"]),
            "kind": "figure",
            "option": row["name"],
            "formats": row.get("tags", {}).get("formats", []),
            "default": row.get("default"),
            "schema_summary": _schema_summary(row.get("schema")),
            "description": _description_text(row.get("description", "")),
        }
        for row in figures_rows
    ] + [
        {
            "id": _slugify(row["name"]),
            "kind": "table",
            "option": row["name"],
            "formats": row.get("tags", {}).get("formats", []),
            "default": row.get("default"),
            "schema_summary": _schema_summary(row.get("schema")),
            "description": _description_text(row.get("description", "")),
        }
        for row in table_rows
    ]

    callout_items = [
        {
            "id": "bootstrap-html",
            "renderer_tier": "bootstrap-html",
            "formats": ["html"],
            "appearance_modes": ["default", "simple", "minimal"],
            "features": ["collapsible", "theme-aware", "dark-mode-aware"],
            "structure_notes": "Header and body containers with icon and title regions.",
        },
        {
            "id": "revealjs-html",
            "renderer_tier": "revealjs-html",
            "formats": ["revealjs"],
            "appearance_modes": ["default", "simple", "minimal"],
            "features": ["slide-aware scaling", "dark-background adaptation"],
            "structure_notes": "Flatter structure optimized for slide reading instead of collapsible chrome.",
        },
        {
            "id": "standalone-html",
            "renderer_tier": "standalone-html",
            "formats": ["epub", "gfm", "plain-html"],
            "appearance_modes": ["default", "simple", "minimal"],
            "features": ["inline-css", "fixed-colors", "no-framework-dependency"],
            "structure_notes": "Standalone HTML callouts trade theming depth for portability.",
        },
        {
            "id": "appearance-default",
            "renderer_tier": "appearance",
            "formats": ["html", "revealjs", "epub"],
            "appearance_modes": ["default"],
            "features": ["colored-header", "full-border-treatment"],
            "structure_notes": "Best when the callout should stand out as a named block.",
        },
        {
            "id": "appearance-simple",
            "renderer_tier": "appearance",
            "formats": ["html", "revealjs", "epub"],
            "appearance_modes": ["simple"],
            "features": ["left-border", "lighter-visual-weight"],
            "structure_notes": "Best when the content should remain lightweight and low-distraction.",
        },
        {
            "id": "appearance-minimal",
            "renderer_tier": "appearance",
            "formats": ["html", "revealjs", "epub"],
            "appearance_modes": ["minimal"],
            "features": ["simple-style", "icon-suppressed"],
            "structure_notes": "Useful for understated notes where iconography would add clutter.",
        },
    ]

    publishing_items = [
        {
            "id": "book-project",
            "project_type": "book",
            "primary_outputs": ["html", "pdf"],
            "structure": ["index", "intro", "summary", "references"],
            "supporting_assets": ["references.bib"],
            "layout_notes": "Multi-chapter long-form structure with shared bibliography and HTML/PDF parity.",
            "source_template": "references/quarto/raw/src/resources/projects/book/templates/_quarto.ejs.yml",
        },
        {
            "id": "website-project",
            "project_type": "website",
            "primary_outputs": ["html"],
            "structure": ["navbar", "home", "about", "shared theme", "styles.css"],
            "supporting_assets": ["toc", "brand theme"],
            "layout_notes": "Navigation-led publishing structure for docs, hubs, and content sites.",
            "source_template": "references/quarto/raw/src/resources/projects/website/templates/_quarto.ejs.yml",
        },
        {
            "id": "manuscript-project",
            "project_type": "manuscript",
            "primary_outputs": ["html", "docx", "jats"],
            "structure": ["article entrypoint", "comments", "freeze execution"],
            "supporting_assets": ["peer review comments", "submission-oriented outputs"],
            "layout_notes": "Submission-ready long-form layout pattern for research and report workflows.",
            "source_template": "references/quarto/raw/src/resources/projects/manuscript/templates/_quarto.ejs.yml",
        },
    ]

    formatting_rows = _load_yaml(
        raw_dir / "src" / "resources" / "schema" / "document-formatting.yml"
    )
    typst_rows = _load_yaml(
        raw_dir / "src" / "resources" / "schema" / "document-typst.yml"
    )
    split_level = next(row for row in formatting_rows if row["name"] == "split-level")
    theorem_appearance = next(
        row for row in typst_rows if row["name"] == "theorem-appearance"
    )
    margin_geometry = next(
        row for row in typst_rows if row["name"] == "margin-geometry"
    )
    longform_items = [
        {
            "id": "typst-modular-template",
            "pattern": "typst-modular-template",
            "outputs": ["typst", "pdf"],
            "modules": [
                "definitions.typ",
                "typst-template.typ",
                "page.typ",
                "typst-show.typ",
                "notes.typ",
                "biblio.typ",
            ],
            "notes": "Quarto splits Pandoc typst templates into reusable partials so long-form documents can layer typography, notes, and bibliography cleanly.",
            "source_note": "references/quarto/raw/llm-docs/pandoc-quarto-typst-templates.md",
        },
        {
            "id": "epub-split-level",
            "pattern": "epub-split-level",
            "outputs": ["epub", "chunkedhtml"],
            "schema_summary": _schema_summary(split_level.get("schema")),
            "default": split_level.get("default"),
            "notes": _description_text(split_level.get("description")),
            "source_note": "references/quarto/raw/src/resources/schema/document-formatting.yml",
        },
        {
            "id": "typst-theorem-appearance",
            "pattern": "typst-theorem-appearance",
            "outputs": ["typst"],
            "schema_summary": _schema_summary(theorem_appearance.get("schema")),
            "default": theorem_appearance.get("default"),
            "notes": _description_text(theorem_appearance.get("description")),
            "source_note": "references/quarto/raw/src/resources/schema/document-typst.yml",
        },
        {
            "id": "typst-margin-geometry",
            "pattern": "typst-margin-geometry",
            "outputs": ["typst"],
            "schema_summary": _schema_summary(margin_geometry.get("schema")),
            "default": margin_geometry.get("default"),
            "notes": _description_text(margin_geometry.get("description")),
            "source_note": "references/quarto/raw/src/resources/schema/document-typst.yml",
        },
    ]

    _write_dataset(
        normalized_dir / "document_layout_options.json",
        dataset_id="document_layout_options",
        source_family=family,
        description="Document layout controls normalized from Quarto schema definitions.",
        generated_from=["references/quarto/raw/src/resources/schema/document-layout.yml"],
        items=layout_items,
    )
    _write_dataset(
        normalized_dir / "table_figure_conventions.json",
        dataset_id="table_figure_conventions",
        source_family=family,
        description="Table and figure defaults normalized from Quarto schema definitions.",
        generated_from=[
            "references/quarto/raw/src/resources/schema/document-figures.yml",
            "references/quarto/raw/src/resources/schema/cell-table.yml",
        ],
        items=table_figure_items,
    )
    _write_dataset(
        normalized_dir / "callout_patterns.json",
        dataset_id="callout_patterns",
        source_family=family,
        description="Callout renderer tiers and appearance modes derived from Quarto HTML architecture docs.",
        generated_from=["references/quarto/raw/llm-docs/callout-styling-html.md"],
        items=callout_items,
    )
    _write_dataset(
        normalized_dir / "publishing_patterns.json",
        dataset_id="publishing_patterns",
        source_family=family,
        description="Project-level publishing structures derived from Quarto project templates.",
        generated_from=[
            "references/quarto/raw/src/resources/projects/book/templates/_quarto.ejs.yml",
            "references/quarto/raw/src/resources/projects/website/templates/_quarto.ejs.yml",
            "references/quarto/raw/src/resources/projects/manuscript/templates/_quarto.ejs.yml",
        ],
        items=publishing_items,
    )
    _write_dataset(
        normalized_dir / "longform_structure_patterns.json",
        dataset_id="longform_structure_patterns",
        source_family=family,
        description="Long-form formatting and template patterns derived from Quarto Typst and formatting docs.",
        generated_from=[
            "references/quarto/raw/llm-docs/pandoc-quarto-typst-templates.md",
            "references/quarto/raw/src/resources/schema/document-formatting.yml",
            "references/quarto/raw/src/resources/schema/document-typst.yml",
        ],
        items=longform_items,
    )


def main() -> None:
    _normalize_ui_ux()
    _normalize_vega_lite()
    _normalize_quarto()


if __name__ == "__main__":
    main()
