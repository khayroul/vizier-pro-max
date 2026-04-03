"""Ambient local-reference routing and context assembly for Hermes-native tasks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from references.query import (
    search_chart_patterns,
    search_color_systems,
    search_landing_patterns,
    search_quarto_layouts,
    search_report_layouts,
    search_typography_pairings,
    search_ui_styles,
    search_ux_guidelines,
)

_DEFAULT_TOP_K = 3
_TURN_CONTEXT_TOP_K = 1


@dataclass(frozen=True)
class AmbientReferenceRoute:
    """Deterministic mapping from task family to local reference searches."""

    task_family: str
    tool_names: tuple[str, ...]
    trigger_keywords: tuple[str, ...]
    description: str
    auxiliary_tool_names: tuple[str, ...] = ()


_SEARCH_FUNCTIONS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "search_ui_styles": search_ui_styles,
    "search_ux_guidelines": search_ux_guidelines,
    "search_landing_patterns": search_landing_patterns,
    "search_typography_pairings": search_typography_pairings,
    "search_color_systems": search_color_systems,
    "search_chart_patterns": search_chart_patterns,
    "search_report_layouts": search_report_layouts,
    "search_quarto_layouts": search_quarto_layouts,
}

_ROUTES: dict[str, AmbientReferenceRoute] = {
    "visual": AmbientReferenceRoute(
        task_family="visual",
        tool_names=("search_ui_styles", "search_ux_guidelines"),
        auxiliary_tool_names=(
            "search_landing_patterns",
            "search_typography_pairings",
            "search_color_systems",
        ),
        trigger_keywords=(
            "poster",
            "flyer",
            "banner",
            "social",
            "graphic",
            "visual",
            "landing page",
            "landing",
            "hero",
            "ui",
            "ux",
            "headline",
            "cta",
        ),
        description=(
            "visual/UI/poster -> search_ui_styles + search_ux_guidelines, "
            "plus landing-pattern, typography-pairing, and color-system probes"
        ),
    ),
    "chart": AmbientReferenceRoute(
        task_family="chart",
        tool_names=("search_chart_patterns",),
        trigger_keywords=(
            "chart",
            "graph",
            "analytics",
            "analytic",
            "dashboard",
            "metric",
            "kpi",
            "infographic",
            "trend",
            "data",
        ),
        description="chart/infographic/analytics -> search_chart_patterns",
    ),
    "document": AmbientReferenceRoute(
        task_family="document",
        tool_names=("search_report_layouts", "search_quarto_layouts"),
        trigger_keywords=(
            "report",
            "document",
            "proposal",
            "brief",
            "whitepaper",
            "ebook",
            "long-form",
            "publishing",
            "layout",
            "manuscript",
        ),
        description=(
            "report/document/long-form/publishing -> "
            "search_report_layouts + search_quarto_layouts"
        ),
    ),
}


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return " ".join(
            fragment
            for fragment in (_coerce_text(item) for item in value.values())
            if fragment
        )
    if isinstance(value, (list, tuple, set)):
        return " ".join(
            fragment
            for fragment in (_coerce_text(item) for item in value)
            if fragment
        )
    return str(value).strip()


def _join_query_parts(*parts: Any) -> str:
    fragments = [_coerce_text(part) for part in parts]
    return " ".join(fragment for fragment in fragments if fragment)


def _take_items(value: Any, *, limit: int = 3) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(items[:limit])
    return _coerce_text(value)


def _clip_sentence(text: str, *, limit: int = 220) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    haystack = text.lower()
    return any(token in haystack for token in tokens)


def _select_visual_ux_guidance(result: dict[str, Any]) -> str:
    issue = _coerce_text(result.get("issue"))
    practice = _coerce_text(result.get("recommended_practice"))
    combined = _join_query_parts(issue, practice).lower()
    if not combined:
        return ""
    if not _contains_any(
        combined,
        (
            "heading",
            "headline",
            "typography",
            "hierarchy",
            "contrast",
            "readability",
            "readable",
            "spacing",
            "whitespace",
            "button",
            "cta",
            "layout",
            "grid",
            "focus",
        ),
    ):
        return ""
    return _clip_sentence(practice or issue, limit=140)


def _select_visual_cta_guidance(result: dict[str, Any]) -> str:
    placement = _coerce_text(result.get("primary_cta_placement"))
    optimization = _coerce_text(result.get("conversion_optimization"))
    placement_lower = placement.lower()
    optimization_lower = optimization.lower()
    fragments: list[str] = []
    if _contains_any(
        placement_lower,
        (
            "hero",
            "above the fold",
            "above-fold",
            "below the headline",
            "below headline",
            "sticky",
            "footer",
            "bottom",
            "rail",
            "side",
        ),
    ):
        fragments.append(placement)
    if _contains_any(
        optimization_lower,
        (
            "single primary",
            "primary action",
            "one action",
            "clear action",
            "deadline",
            "social proof",
            "trust",
            "urgent",
            "clarity",
        ),
    ):
        fragments.append(optimization)
    return _clip_sentence(" ".join(fragment for fragment in fragments if fragment), limit=150)


def _summarize_ui_style(result: dict[str, Any]) -> str:
    name = _coerce_text(result.get("name")) or "UI style"
    best_for = _take_items(result.get("best_for"))
    accessibility = _coerce_text(result.get("accessibility"))
    parts = [f"UI style reference: {name}."]
    if best_for:
        parts.append(f"Best for {best_for}.")
    if accessibility:
        parts.append(f"Accessibility note: {accessibility}.")
    return _clip_sentence(" ".join(parts))


def _summarize_ux_guideline(result: dict[str, Any]) -> str:
    issue = _coerce_text(result.get("issue")) or "UX guideline"
    platform = _coerce_text(result.get("platform"))
    practice = _coerce_text(result.get("recommended_practice"))
    avoid = _coerce_text(result.get("avoid"))
    parts = [f"UX guidance: {issue}{f' ({platform})' if platform else ''}."]
    if practice:
        parts.append(f"Use {practice}.")
    if avoid:
        parts.append(f"Avoid {avoid}.")
    return _clip_sentence(" ".join(parts))


def _summarize_landing_pattern(result: dict[str, Any]) -> str:
    pattern_name = _coerce_text(result.get("pattern_name")) or "Landing pattern"
    cta_placement = _coerce_text(result.get("primary_cta_placement"))
    conversion = _coerce_text(result.get("conversion_optimization"))
    parts = [f"Landing pattern: {pattern_name}."]
    if cta_placement:
        parts.append(f"CTA placement: {cta_placement}.")
    if conversion:
        parts.append(conversion)
    return _clip_sentence(" ".join(parts))


def _summarize_typography_pairing(result: dict[str, Any]) -> str:
    pairing = _coerce_text(result.get("pairing_name")) or "Typography pairing"
    best_for = _take_items(result.get("best_for"))
    notes = _coerce_text(result.get("notes"))
    parts = [f"Typography pairing: {pairing}."]
    if best_for:
        parts.append(f"Best for {best_for}.")
    if notes:
        parts.append(notes)
    return _clip_sentence(" ".join(parts))


def _summarize_color_system(result: dict[str, Any]) -> str:
    product_type = _coerce_text(result.get("product_type")) or "Color system"
    notes = _coerce_text(result.get("notes"))
    accent = _coerce_text(result.get("accent"))
    background = _coerce_text(result.get("background"))
    parts = [f"Color system: {product_type}."]
    if accent or background:
        parts.append(
            f"Use accent {accent or 'n/a'} against background {background or 'n/a'}."
        )
    if notes:
        parts.append(notes)
    return _clip_sentence(" ".join(parts))


def _summarize_chart_pattern(result: dict[str, Any]) -> str:
    title = (
        _coerce_text(result.get("title"))
        or _coerce_text(result.get("data_type"))
        or "Chart pattern"
    )
    best_chart = _coerce_text(result.get("best_chart_type"))
    analytic_goal = _coerce_text(result.get("analytic_goal"))
    when_to_use = _coerce_text(result.get("when_to_use"))
    avoid = (
        _coerce_text(result.get("when_not_to_use"))
        or _coerce_text(result.get("avoid_when"))
    )
    parts = [f"Chart pattern: {title}."]
    if best_chart:
        parts.append(f"Best chart type: {best_chart}.")
    elif analytic_goal:
        parts.append(f"{analytic_goal}.")
    if when_to_use:
        parts.append(f"Use when {when_to_use}.")
    if avoid:
        parts.append(f"Avoid when {avoid}.")
    return _clip_sentence(" ".join(parts))


def _summarize_report_layout(result: dict[str, Any]) -> str:
    dataset_id = _coerce_text(result.get("dataset_id"))
    if dataset_id == "publishing_patterns":
        project_type = _coerce_text(result.get("project_type")) or "Publishing pattern"
        layout_notes = _coerce_text(result.get("layout_notes"))
        outputs = _take_items(result.get("primary_outputs"))
        parts = [f"Publishing layout: {project_type}."]
        if outputs:
            parts.append(f"Primary outputs: {outputs}.")
        if layout_notes:
            parts.append(layout_notes)
        return _clip_sentence(" ".join(parts))

    subject = (
        _coerce_text(result.get("pattern"))
        or _coerce_text(result.get("option"))
        or _coerce_text(result.get("renderer_tier"))
        or "Document layout pattern"
    )
    detail = (
        _coerce_text(result.get("notes"))
        or _coerce_text(result.get("description"))
        or _coerce_text(result.get("layout_notes"))
        or _coerce_text(result.get("structure_notes"))
    )
    features = _take_items(result.get("features"))
    parts = [f"Document layout reference: {subject}."]
    if detail:
        parts.append(detail)
    if features:
        parts.append(f"Features: {features}.")
    return _clip_sentence(" ".join(parts))


_GUIDANCE_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "search_ui_styles": _summarize_ui_style,
    "search_ux_guidelines": _summarize_ux_guideline,
    "search_landing_patterns": _summarize_landing_pattern,
    "search_typography_pairings": _summarize_typography_pairing,
    "search_color_systems": _summarize_color_system,
    "search_chart_patterns": _summarize_chart_pattern,
    "search_report_layouts": _summarize_report_layout,
    "search_quarto_layouts": _summarize_report_layout,
}


def list_ambient_reference_routes() -> tuple[AmbientReferenceRoute, ...]:
    """Return the supported task-family routing table."""
    return tuple(
        _ROUTES[task_family] for task_family in ("visual", "chart", "document")
    )


def infer_ambient_reference_families(text: str) -> tuple[str, ...]:
    """Infer relevant task families from free-form request text."""
    haystack = text.lower()
    scored: list[tuple[int, int, str]] = []
    for priority, task_family in enumerate(("visual", "chart", "document"), start=1):
        route = _ROUTES[task_family]
        score = sum(1 for keyword in route.trigger_keywords if keyword in haystack)
        if score == 0:
            continue
        scored.append((-score, priority, task_family))
    scored.sort()
    return tuple(task_family for _, _, task_family in scored)


def _run_search(
    tool_name: str,
    query: str,
    *,
    top_k: int,
    consult_kind: str,
) -> dict[str, Any]:
    results = _SEARCH_FUNCTIONS[tool_name](query, top_k=top_k)
    guidance = ""
    if results:
        guidance = _GUIDANCE_BUILDERS[tool_name](results[0])
    return {
        "tool_name": tool_name,
        "query": query,
        "consult_kind": consult_kind,
        "results": results,
        "match_count": len(results),
        "guidance": guidance,
    }


def _result_label(result: dict[str, Any]) -> str:
    for key in (
        "name",
        "issue",
        "pattern_name",
        "pairing_name",
        "product_type",
        "title",
        "pattern",
        "option",
    ):
        value = _coerce_text(result.get(key))
        if value:
            return value
    return _coerce_text(result.get("id")) or "reference"


def _influence_reason(tool_name: str, result: dict[str, Any]) -> str:
    if tool_name == "search_ui_styles":
        motif = dict(result.get("visual_motif") or {})
        checklist = _take_items(motif.get("implementation_checklist"))
        return _clip_sentence(
            _join_query_parts(
                "Sets the overall visual direction.",
                checklist,
            ),
            limit=180,
        )
    if tool_name == "search_ux_guidelines":
        return _clip_sentence(
            _join_query_parts(
                result.get("recommended_practice"),
                "Avoid:",
                result.get("avoid"),
            ),
            limit=180,
        )
    if tool_name == "search_landing_patterns":
        return _clip_sentence(
            _join_query_parts(
                "Shapes CTA placement and section flow.",
                result.get("primary_cta_placement"),
                result.get("conversion_optimization"),
            ),
            limit=180,
        )
    if tool_name == "search_typography_pairings":
        return _clip_sentence(
            _join_query_parts(
                "Sharpens headline/body hierarchy.",
                result.get("notes"),
            ),
            limit=180,
        )
    if tool_name == "search_color_systems":
        return _clip_sentence(
            _join_query_parts(
                "Biases contrast and premium color separation.",
                result.get("notes"),
            ),
            limit=180,
        )
    return _clip_sentence(_coerce_text(result.get("notes")) or "Reference influence.")


def _build_material_influences(searches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    influences: list[dict[str, Any]] = []
    for search in searches:
        if not search["results"]:
            continue
        result = dict(search["results"][0])
        influences.append(
            {
                "tool_name": search["tool_name"],
                "consult_kind": search["consult_kind"],
                "record_id": _coerce_text(result.get("id")),
                "label": _result_label(result),
                "reference_family": _coerce_text(result.get("reference_family")),
                "dataset_id": _coerce_text(result.get("dataset_id")),
                "why_it_matters": _influence_reason(search["tool_name"], result),
            }
        )
    return influences


def _first_result(searches: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for search in searches:
        if search["tool_name"] == tool_name and search["results"]:
            return dict(search["results"][0])
    return {}


def _infer_visual_design_axes(
    *,
    query: str,
    style_result: dict[str, Any],
    landing_result: dict[str, Any],
) -> dict[str, Any]:
    query_lower = query.lower()
    style_id = _coerce_text(style_result.get("id")).lower()
    style_name = _coerce_text(style_result.get("name")).lower()
    landing_id = _coerce_text(landing_result.get("id")).lower()

    if any(token in style_id for token in ("swiss", "editorial")) or any(
        token in query_lower for token in ("swiss", "editorial", "grid", "magazine")
    ):
        return {
            "composition_mode": "editorial_split",
            "template_candidates": [
                "editorial-split-square",
                "floating-card-square",
                "center-stage-square",
            ],
            "reason": "Swiss/editorial cues favor a disciplined split or grid-led composition.",
        }
    if any(
        token in query_lower
        for token in ("dashboard", "analytics", "app", "ui", "saas", "interface")
    ):
        return {
            "composition_mode": "card_showcase",
            "template_candidates": [
                "floating-card-square",
                "center-stage-square",
                "editorial-split-square",
            ],
            "reason": "UI/product-surface cues favor a framed hero or card-showcase composition.",
        }
    if any(
        token in query_lower
        for token in (
            "product",
            "launch",
            "drop",
            "limited release",
            "limited-edition",
            "coffee",
            "drink",
            "bottle",
            "can",
            "packaging",
            "hero-forward",
        )
    ):
        return {
            "composition_mode": "product_hero",
            "template_candidates": [
                "center-stage-square",
                "hero-bottom-text-square",
                "floating-card-square",
            ],
            "reason": "Product-launch cues favor one dominant object hero with a clear purchase-ready CTA rail.",
        }
    if any(
        token in query_lower for token in ("event", "festival", "concert", "music", "retro", "synthwave")
    ) or "bold typography" in style_name:
        return {
            "composition_mode": "type_driven",
            "template_candidates": [
                "bold-knockout-square",
                "stacked-type-square",
                "hero-bottom-text-square",
            ],
            "reason": "Event and retro cues favor a headline-led poster with a visible hero texture behind the type.",
        }
    if "hero" in landing_id or "hero-centric" in style_id or "hero-centric" in style_name:
        return {
            "composition_mode": "hero_dominant",
            "template_candidates": [
                "hero-bottom-text-square",
                "center-stage-square",
                "social-post",
            ],
            "reason": "Hero-first references point to a single dominant focal scene with protected copy space.",
        }
    if "minimal-direct" in style_id or any(
        token in query_lower for token in ("minimal", "donation", "trust", "fundraiser")
    ):
        return {
            "composition_mode": "minimal_direct",
            "template_candidates": [
                "hero-bottom-text-square",
                "editorial-split-square",
                "social-post",
            ],
            "reason": "Trust-sensitive/minimal cues favor a restrained, whitespace-heavy composition.",
        }
    return {
        "composition_mode": "hero_dominant",
        "template_candidates": [
            "hero-bottom-text-square",
            "center-stage-square",
            "social-post",
        ],
        "reason": "Default to a premium hero-led composition with strong focal hierarchy.",
    }


def _build_visual_art_direction(
    *,
    query: str,
    searches: list[dict[str, Any]],
) -> dict[str, Any]:
    style_result = _first_result(searches, "search_ui_styles")
    ux_result = _first_result(searches, "search_ux_guidelines")
    landing_result = _first_result(searches, "search_landing_patterns")
    typography_result = _first_result(searches, "search_typography_pairings")
    color_result = _first_result(searches, "search_color_systems")

    axes = _infer_visual_design_axes(
        query=query,
        style_result=style_result,
        landing_result=landing_result,
    )
    mode = axes["composition_mode"]

    composition_map = {
        "type_driven": (
            "Treat the headline as a graphic element and keep one dramatic supporting visual or texture behind it, not a busy collage."
        ),
        "editorial_split": (
            "Use a disciplined split or asymmetrical grid with one confident focal plane and deliberate negative space for copy."
        ),
        "card_showcase": (
            "Use a framed hero/product surface that occupies the visual center so the design feels intentional instead of generic."
        ),
        "product_hero": (
            "Build the layout around one dominant product hero with confident negative space and a CTA rail that reads immediately."
        ),
        "minimal_direct": (
            "Keep the composition spare and premium, with one focal move and generous whitespace around the message."
        ),
        "hero_dominant": (
            "Build a hero-first composition where one subject clearly dominates the frame and the copy area stays calm."
        ),
    }
    hero_map = {
        "type_driven": (
            "Keep the hero element large and graphic, but reserve enough quiet space that big typography still feels clean and premium."
        ),
        "editorial_split": (
            "Bias the hero to one side of the frame and leave the opposite side cleaner for overlay hierarchy."
        ),
        "card_showcase": (
            "Make the hero subject read at a glance with crisp edges and enough scale to feel premium, not thumbnail-sized."
        ),
        "product_hero": (
            "Let the product occupy roughly half the frame with polished lighting, clean edges, and protected negative space around the CTA block."
        ),
        "minimal_direct": (
            "Use one calm hero subject with minimal clutter and no muddy background textures behind the text zone."
        ),
        "hero_dominant": (
            "Let the hero subject occupy roughly 60-75% of the frame with obvious focal contrast and controlled lighting."
        ),
    }
    typography_note = _coerce_text(typography_result.get("notes"))
    ux_guidance = _select_visual_ux_guidance(ux_result)
    cta_reference = _select_visual_cta_guidance(landing_result)
    readability = _join_query_parts(
        "Reserve a high-contrast text zone with low visual noise behind body copy.",
        ux_guidance,
        typography_note,
    )
    cta = _join_query_parts(
        "Give the CTA one dominant action zone and avoid burying it under secondary decoration.",
        cta_reference,
    )
    color = _join_query_parts(
        "Keep the palette intentional with one accent doing the CTA work instead of multiple competing highlight colors.",
        color_result.get("notes"),
    )
    return {
        "composition_mode": mode,
        "template_candidates": list(axes["template_candidates"]),
        "template_reason": str(axes["reason"]),
        "composition": composition_map[mode],
        "hero": hero_map[mode],
        "readability": _clip_sentence(readability or "Protect readability with strong hierarchy and contrast."),
        "cta": _clip_sentence(cta or "Keep one clear CTA with strong contrast and obvious priority."),
        "copy": "Keep the headline concise, the body to one short supporting beat, and the CTA action-led.",
        "polish": _clip_sentence(
            color
            or "Favor premium lighting, controlled contrast, and deliberate negative space over flat generic backgrounds."
        ),
        "recommended_fonts": {
            "heading_font": _coerce_text(typography_result.get("heading_font")),
            "body_font": _coerce_text(typography_result.get("body_font")),
            "pairing_name": _coerce_text(typography_result.get("pairing_name")),
        },
        "recommended_colors": {
            "primary": _coerce_text(color_result.get("primary")),
            "secondary": _coerce_text(color_result.get("secondary")),
            "accent": _coerce_text(color_result.get("accent")),
            "background": _coerce_text(color_result.get("background")),
            "foreground": _coerce_text(color_result.get("foreground")),
        },
        "supporting_references": {
            "style": _result_label(style_result) if style_result else "",
            "ux": _result_label(ux_result) if ux_result else "",
            "landing": _result_label(landing_result) if landing_result else "",
            "typography": _result_label(typography_result) if typography_result else "",
            "color": _result_label(color_result) if color_result else "",
        },
    }


def _build_context(
    *,
    task_family: str,
    queries: list[str],
    metadata: dict[str, Any],
    top_k: int = _DEFAULT_TOP_K,
) -> dict[str, Any]:
    route = _ROUTES[task_family]
    normalized_queries = [query for query in queries if query.strip()]
    searches = [
        _run_search(tool_name, query, top_k=top_k, consult_kind="lookup_tool")
        for query in normalized_queries
        for tool_name in route.tool_names
    ]
    searches.extend(
        _run_search(tool_name, query, top_k=top_k, consult_kind="dataset_probe")
        for query in normalized_queries
        for tool_name in route.auxiliary_tool_names
    )
    guidance = " ".join(
        search["guidance"] for search in searches if search["guidance"]
    ).strip()
    return {
        "task_family": task_family,
        "auto_consulted": bool(searches),
        "query_count": len(normalized_queries),
        "tool_names": list(route.tool_names),
        "auxiliary_tool_names": list(route.auxiliary_tool_names),
        "route_description": route.description,
        "lookup_tools_used": sorted(
            {
                search["tool_name"]
                for search in searches
                if search["consult_kind"] == "lookup_tool"
            }
        ),
        "dataset_searches_used": sorted(
            {
                search["tool_name"]
                for search in searches
                if search["consult_kind"] == "dataset_probe"
            }
        ),
        "reference_families_consulted": sorted(
            {
                _coerce_text(result.get("reference_family"))
                for search in searches
                for result in search["results"]
                if _coerce_text(result.get("reference_family"))
            }
        ),
        "datasets_consulted": sorted(
            {
                _coerce_text(result.get("dataset_id"))
                for search in searches
                for result in search["results"]
                if _coerce_text(result.get("dataset_id"))
            }
        ),
        "searches": searches,
        "guidance": guidance,
        "material_influences": _build_material_influences(searches),
        "metadata": metadata,
    }


def build_visual_reference_context(
    *,
    headline: str,
    body: str,
    image_prompt: str = "",
    brand_name: str = "",
    brief: str = "",
    style_hint: str = "",
    top_k: int = _DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Assemble automatic local design guidance for poster/UI tasks."""
    query = _join_query_parts(headline, body, image_prompt, brand_name, brief, style_hint)
    context = _build_context(
        task_family="visual",
        queries=[query],
        metadata={
            "headline": headline,
            "body": body,
            "image_prompt": image_prompt,
            "brand_name": brand_name,
            "brief": brief,
            "style_hint": style_hint,
        },
        top_k=top_k,
    )
    art_direction = _build_visual_art_direction(query=query, searches=context["searches"])
    context["art_direction"] = art_direction
    context["guidance"] = " ".join(
        part
        for part in (
            context["guidance"],
            art_direction["composition"],
            art_direction["readability"],
            art_direction["cta"],
            art_direction["polish"],
        )
        if part
    ).strip()
    return context


def build_chart_reference_context(
    *,
    title: str,
    charts: list[dict[str, object]] | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Assemble automatic local chart guidance for analytics/infographic tasks."""
    queries: list[str] = []
    for chart in charts or []:
        chart_title = _coerce_text(chart.get("title"))
        chart_type = _coerce_text(chart.get("chart_type"))
        section_heading = _coerce_text(chart.get("section_heading"))
        queries.append(_join_query_parts(chart_title or section_heading, chart_type, title))
    if not queries:
        queries.append(_join_query_parts(title))
    return _build_context(
        task_family="chart",
        queries=queries,
        metadata={
            "title": title,
            "charts": charts or [],
        },
        top_k=top_k,
    )


def build_document_reference_context(
    *,
    title: str,
    subtitle: str = "",
    profile: str = "",
    package_mode: str = "",
    document_titles: list[str] | None = None,
    section_headings: list[str] | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Assemble automatic local layout guidance for report/document tasks."""
    query = _join_query_parts(
        title,
        subtitle,
        profile.replace("_", " "),
        package_mode.replace("_", " "),
        document_titles or [],
        (section_headings or [])[:8],
    )
    return _build_context(
        task_family="document",
        queries=[query],
        metadata={
            "title": title,
            "subtitle": subtitle,
            "profile": profile,
            "package_mode": package_mode,
            "document_titles": document_titles or [],
            "section_headings": section_headings or [],
        },
        top_k=top_k,
    )


def build_ambient_turn_context(user_message: str) -> str:
    """Return a Hermes pre-LLM reminder for local reference capabilities."""
    lines = [
        "Hermes has pinned local reference corpora and should consult them automatically when relevant:",
        "- visual/UI/poster -> search_ui_styles + search_ux_guidelines",
        "- chart/infographic/analytics -> search_chart_patterns",
        "- report/document/long-form/publishing -> search_report_layouts + search_quarto_layouts",
        "- These corpora are local reference layers only. Hermes remains the only runtime; do not execute UI UX Pro Max, Vega-Lite, or Quarto.",
    ]

    families = infer_ambient_reference_families(user_message)
    if not families:
        return "\n".join(lines)

    lines.append("Automatic local reference guidance for this request:")
    for task_family in families[:2]:
        if task_family == "visual":
            context = build_visual_reference_context(
                headline=user_message,
                body="",
                top_k=_TURN_CONTEXT_TOP_K,
            )
        elif task_family == "chart":
            context = build_chart_reference_context(
                title=user_message,
                top_k=_TURN_CONTEXT_TOP_K,
            )
        else:
            context = build_document_reference_context(
                title=user_message,
                top_k=_TURN_CONTEXT_TOP_K,
            )
        if context["guidance"]:
            lines.append(f"- {context['guidance']}")
    return "\n".join(lines)
