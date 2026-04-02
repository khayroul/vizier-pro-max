"""Long-form novel pipeline built on the shared publishing spine."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from middleware.quality_scorer import QualityProperty
from pipelines.longform.spine import (
    build_metadata,
    ensure_output_dir,
    normalize_chapters,
    render_chapter_html,
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
    chapters: list[dict[str, object]],
    output_dir: str = "output/longform/novel",
    subtitle: str = "",
    date: str = "",
    cover_path: str = "",
    brand: dict[str, object] | None = None,
    export_pdf: bool = True,
    export_epub: bool = True,
) -> dict[str, Any]:
    """Generate a novel package with HTML, PDF, and EPUB exports."""
    metadata = build_metadata(
        title=title,
        author=author,
        subtitle=subtitle,
        date=date,
        cover_path=cover_path,
        brand=brand,
    )
    normalized_chapters = normalize_chapters(chapters)
    out_dir = ensure_output_dir(output_dir)
    html_path = out_dir / "manuscript.html"
    pdf_path = out_dir / "manuscript.pdf"
    epub_path = out_dir / "manuscript.epub"

    chapter_html = [
        render_chapter_html(
            metadata,
            chapter_number=idx,
            title=chapter.title,
            body=chapter.body,
            callout=chapter.summary,
            illustration_path=chapter.illustration_path,
        )
        for idx, chapter in enumerate(normalized_chapters, start=1)
    ]
    manuscript_html = wrap_book_shell_html(
        metadata,
        f"{render_title_page_html(metadata, 'Novel')}"
        f"{''.join(chapter_html)}",
    )
    write_text(html_path, manuscript_html)

    result: dict[str, Any] = {
        "status": "completed",
        "title": metadata.title,
        "chapter_count": len(normalized_chapters),
        "html_path": str(html_path),
    }

    if export_pdf:
        render_pdf(html_content=manuscript_html, output_path=str(pdf_path))
        result["pdf_path"] = str(pdf_path)

    if export_epub:
        assemble_epub(
            title=metadata.title,
            author=metadata.author,
            chapters=[
                {"title": chapter.title, "html": rendered}
                for chapter, rendered in zip(normalized_chapters, chapter_html, strict=True)
            ],
            cover_path=metadata.cover_path,
            output_path=str(epub_path),
        )
        result["epub_path"] = str(epub_path)

    average_chapter_length = sum(
        len(chapter.body) for chapter in normalized_chapters
    ) / len(normalized_chapters)
    quality_props = [
        QualityProperty(
            name="chapter_count",
            passed=len(normalized_chapters) >= 3,
            pass_delta=1.5,
            fail_delta=1.5,
            detail=f"found {len(normalized_chapters)} chapters",
            is_gate=True,
        ),
        QualityProperty(
            name="chapter_length",
            passed=average_chapter_length >= 250,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"average chapter length {average_chapter_length:.1f} chars",
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
        pipeline="novel_generate",
        properties=quality_props,
    )

    logger.info(
        "novel_generated",
        output_dir=str(out_dir),
        chapter_count=len(normalized_chapters),
    )
    return result
