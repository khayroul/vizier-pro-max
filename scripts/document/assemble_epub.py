"""Assemble an EPUB file from chapter HTML and optional cover art."""
from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def run(
    *,
    title: str,
    author: str,
    chapters: list[dict[str, object]],
    cover_path: str = "",
    output_path: str,
) -> dict[str, str]:
    """Create an EPUB from structured chapter content."""
    if not title:
        msg = "title is required"
        raise ValueError(msg)
    if not author:
        msg = "author is required"
        raise ValueError(msg)
    if not output_path:
        msg = "output_path is required"
        raise ValueError(msg)

    from ebooklib import epub  # type: ignore[import-untyped]

    book = epub.EpubBook()
    book.set_identifier(f"vizier-{title.lower().replace(' ', '-')}")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    cover = Path(cover_path) if cover_path else None
    if cover is not None and cover.exists():
        book.set_cover(cover.name, cover.read_bytes())

    spine: list[object] = ["nav"]
    toc: list[object] = []

    for idx, chapter_data in enumerate(chapters):
        chapter_title = str(chapter_data.get("title", f"Chapter {idx + 1}"))
        chapter_html = str(chapter_data.get("html", ""))
        file_name = f"chapter_{idx + 1}.xhtml"

        chapter = epub.EpubHtml(title=chapter_title, file_name=file_name, lang="en")
        chapter.content = f"<h1>{chapter_title}</h1>{chapter_html}"
        book.add_item(chapter)
        toc.append(chapter)
        spine.append(chapter)

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output), book)
    logger.info("Assembled EPUB", output_path=str(output), chapter_count=len(chapters))
    return {"file_path": str(output)}
