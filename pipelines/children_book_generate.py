"""Children's illustrated book pipeline built on the shared spine."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from middleware.quality_scorer import QualityProperty
from pipelines.longform.spine import (
    build_metadata,
    ensure_output_dir,
    normalize_spreads,
    render_children_spread_html,
    render_title_page_html,
    serialize_quality_report,
    wrap_book_shell_html,
    write_text,
)
from scripts.document.assemble_epub import run as assemble_epub
from scripts.document.render_pdf import run as render_pdf

logger = structlog.get_logger(__name__)


def run(
    *,
    title: str,
    author: str,
    spreads: list[dict[str, object]],
    output_dir: str = "output/longform/children",
    subtitle: str = "",
    date: str = "",
    cover_path: str = "",
    brand: dict[str, object] | None = None,
    export_pdf: bool = True,
    export_epub: bool = True,
) -> dict[str, Any]:
    """Generate an illustrated children's book package."""
    metadata = build_metadata(
        title=title,
        author=author,
        subtitle=subtitle,
        date=date,
        cover_path=cover_path,
        brand=brand,
    )
    normalized_spreads = normalize_spreads(spreads)
    out_dir = ensure_output_dir(output_dir)
    html_path = out_dir / "storybook.html"
    pdf_path = out_dir / "storybook.pdf"
    epub_path = out_dir / "storybook.epub"

    spread_html = [
        render_children_spread_html(
            metadata,
            spread_number=idx,
            spread=spread,
        )
        for idx, spread in enumerate(normalized_spreads, start=1)
    ]
    storybook_html = wrap_book_shell_html(
        metadata,
        f"{render_title_page_html(metadata, 'Illustrated Storybook')}"
        f"{''.join(spread_html)}",
    )
    write_text(html_path, storybook_html)

    result: dict[str, Any] = {
        "status": "completed",
        "title": metadata.title,
        "spread_count": len(normalized_spreads),
        "html_path": str(html_path),
    }

    if export_pdf:
        render_pdf(html_content=storybook_html, output_path=str(pdf_path))
        result["pdf_path"] = str(pdf_path)

    if export_epub:
        assemble_epub(
            title=metadata.title,
            author=metadata.author,
            chapters=[
                {"title": spread.title, "html": rendered}
                for spread, rendered in zip(normalized_spreads, spread_html, strict=True)
            ],
            cover_path=metadata.cover_path,
            output_path=str(epub_path),
        )
        result["epub_path"] = str(epub_path)

    illustrated_spreads = sum(
        1 for spread in normalized_spreads if spread.illustration_path
    )
    quality_props = [
        QualityProperty(
            name="spread_count",
            passed=len(normalized_spreads) >= 6,
            pass_delta=1.5,
            fail_delta=1.5,
            detail=f"found {len(normalized_spreads)} spreads",
            is_gate=True,
        ),
        QualityProperty(
            name="illustration_coverage",
            passed=illustrated_spreads >= max(1, len(normalized_spreads) // 2),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"illustrated spreads {illustrated_spreads}/{len(normalized_spreads)}",
        ),
        QualityProperty(
            name="pdf_export",
            passed=not export_pdf or pdf_path.exists(),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"pdf export requested={export_pdf}",
        ),
        QualityProperty(
            name="epub_export",
            passed=not export_epub or epub_path.exists(),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"epub export requested={export_epub}",
        ),
    ]
    result["quality_report"] = serialize_quality_report(
        pipeline="children_book_generate",
        properties=quality_props,
    )

    logger.info(
        "children_book_generated",
        output_dir=str(out_dir),
        spread_count=len(normalized_spreads),
        illustrated_spreads=illustrated_spreads,
    )
    return result
