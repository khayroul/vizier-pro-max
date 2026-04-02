"""Deck-native Gamma presentation pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from middleware.quality_scorer import QualityProperty
from pipelines.longform.spine import (
    ensure_output_dir,
    serialize_quality_report,
    slugify,
    write_text,
)
from pipelines.structured_nonfiction_generate import (
    gamma_generate_run,
    run as run_structured_nonfiction,
)

logger = structlog.get_logger(__name__)


def _build_brief_markdown(
    *,
    title: str,
    subtitle: str,
    brief: str,
) -> str:
    parts = [f"# {title}"]
    if subtitle.strip():
        parts.extend(["", subtitle.strip()])
    parts.extend(["", brief.strip()])
    return "\n".join(parts).strip() + "\n"


def run(
    *,
    title: str,
    author: str = "Vizier",
    brief: str = "",
    sections: list[dict[str, object]] | None = None,
    charts: list[dict[str, object]] | None = None,
    documents: list[dict[str, object]] | None = None,
    subtitle: str = "",
    output_dir: str = "output/decks",
    profile: str = "proposal",
    package_mode: str = "single_document",
    include_toc: bool = True,
    export_source_pdf: bool = True,
    gamma_export_as: str = "pdf",
    gamma_text_mode: str = "",
    gamma_theme_id: str = "",
    gamma_folder_ids: list[str] | None = None,
    gamma_num_cards: int | None = None,
    gamma_card_split: str = "auto",
    gamma_card_dimensions: str = "16x9",
    gamma_image_source: str = "",
    gamma_image_model: str = "",
    gamma_image_style: str = "",
    gamma_image_style_preset: str = "",
    gamma_text_amount: str = "brief",
    gamma_tone: str = "professional",
    gamma_audience: str = "decision-makers",
    gamma_language: str = "en",
    gamma_additional_instructions: str = "",
    gamma_template_id: str = "",
    gamma_template_prompt: str = "",
    gamma_header_footer: dict[str, object] | None = None,
    gamma_card_options: dict[str, object] | None = None,
    gamma_sharing_options: dict[str, object] | None = None,
    gamma_output_path: str = "",
) -> dict[str, Any]:
    """Generate a presentation deck through Gamma from a brief or structured content."""
    has_structured_content = bool(sections or documents or charts)
    normalized_brief = brief.strip()
    if not title.strip():
        msg = "title is required"
        raise ValueError(msg)
    if not has_structured_content and not normalized_brief:
        msg = "brief or structured content is required"
        raise ValueError(msg)

    effective_output_dir = ensure_output_dir(str(Path(output_dir) / slugify(title)))
    effective_gamma_text_mode = gamma_text_mode.strip() or (
        "condense" if has_structured_content else "generate"
    )
    effective_image_source = gamma_image_source.strip() or (
        "themeAccent" if gamma_theme_id.strip() else "noImages"
    )

    if has_structured_content:
        result = run_structured_nonfiction(
            title=title,
            author=author,
            sections=sections,
            charts=charts,
            documents=documents,
            output_dir=str(effective_output_dir),
            subtitle=subtitle,
            export_pdf=export_source_pdf,
            export_epub=False,
            profile=profile,
            package_mode=package_mode,
            include_toc=include_toc,
            export_gamma=True,
            gamma_format="presentation",
            gamma_text_mode=effective_gamma_text_mode,
            gamma_export_as=gamma_export_as,
            gamma_theme_id=gamma_theme_id,
            gamma_folder_ids=gamma_folder_ids,
            gamma_num_cards=gamma_num_cards,
            gamma_card_split=gamma_card_split,
            gamma_card_dimensions=gamma_card_dimensions,
            gamma_image_source=effective_image_source,
            gamma_image_model=gamma_image_model,
            gamma_image_style=gamma_image_style,
            gamma_image_style_preset=gamma_image_style_preset,
            gamma_text_amount=gamma_text_amount,
            gamma_tone=gamma_tone,
            gamma_audience=gamma_audience,
            gamma_language=gamma_language,
            gamma_additional_instructions=gamma_additional_instructions,
            gamma_template_id=gamma_template_id,
            gamma_template_prompt=gamma_template_prompt,
            gamma_header_footer=gamma_header_footer,
            gamma_card_options=gamma_card_options,
            gamma_sharing_options=gamma_sharing_options,
            gamma_output_path=gamma_output_path,
        )
        result["pipeline"] = "presentation_deck_generate"
        result["source_mode"] = "structured"
        return result

    source_markdown_path = Path(effective_output_dir) / "source.md"
    write_text(
        source_markdown_path,
        _build_brief_markdown(
            title=title,
            subtitle=subtitle,
            brief=normalized_brief,
        ),
    )

    gamma_result = gamma_generate_run(
        input_text=normalized_brief,
        text_mode=effective_gamma_text_mode,
        format="presentation",
        additional_instructions=gamma_additional_instructions,
        export_as=gamma_export_as,
        theme_id=gamma_theme_id,
        folder_ids=gamma_folder_ids,
        num_cards=gamma_num_cards,
        card_split=gamma_card_split,
        card_dimensions=gamma_card_dimensions,
        image_source=effective_image_source,
        image_model=gamma_image_model,
        image_style=gamma_image_style,
        image_style_preset=gamma_image_style_preset,
        text_amount=gamma_text_amount,
        tone=gamma_tone,
        audience=gamma_audience,
        language=gamma_language,
        template_gamma_id=gamma_template_id,
        template_prompt=gamma_template_prompt,
        header_footer=gamma_header_footer,
        card_options=gamma_card_options,
        sharing_options=gamma_sharing_options,
        output_path=gamma_output_path
        or str(Path(effective_output_dir) / f"{slugify(title)}-gamma.{gamma_export_as}"),
    )

    result = {
        "status": "completed",
        "title": title,
        "pipeline": "presentation_deck_generate",
        "source_mode": "brief",
        "source_markdown_path": str(source_markdown_path),
        "gamma_generation": gamma_result,
        "gamma_url": gamma_result.get("gamma_url", ""),
    }
    if gamma_result.get("file_path"):
        result["gamma_file_path"] = gamma_result["file_path"]

    quality_props = [
        QualityProperty(
            name="source_markdown",
            passed=source_markdown_path.exists(),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"source markdown={source_markdown_path}",
            is_gate=True,
        ),
        QualityProperty(
            name="gamma_export",
            passed=bool(gamma_result.get("gamma_url")),
            pass_delta=1.5,
            fail_delta=1.5,
            detail=f"gamma_url={gamma_result.get('gamma_url', '')}",
            is_gate=True,
        ),
        QualityProperty(
            name="deck_file",
            passed=bool(gamma_result.get("file_path")),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"gamma_file_path={gamma_result.get('file_path', '')}",
        ),
    ]
    result["quality_report"] = serialize_quality_report(
        pipeline="presentation_deck_generate",
        properties=quality_props,
    )

    logger.info(
        "presentation_deck_generated",
        title=title,
        source_mode="brief",
        gamma_url=result["gamma_url"],
        output_dir=str(effective_output_dir),
    )
    return result
