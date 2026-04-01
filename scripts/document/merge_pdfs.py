"""pypdf PDF manipulation wrapper."""
from __future__ import annotations

import logging

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_OPERATIONS = {"merge", "extract", "rotate"}


def run(
    *,
    input_paths: list[str],
    output_path: str,
    operation: str,
    pages: list[int] | None = None,
    rotation: int | None = None,
) -> dict[str, str]:
    """Merge, extract, or rotate PDF pages.

    Args:
        input_paths: Paths to input PDF files.
        output_path: Path for output PDF.
        operation: Operation to perform — ``merge``, ``extract``, or ``rotate``.
        pages: Page indices for extract/rotate (0-indexed). Defaults to all pages.
        rotation: Rotation angle in degrees for rotate operation. Defaults to 90.

    Returns:
        Dict with ``file_path`` key pointing to the output PDF.

    Raises:
        ValueError: If ``operation`` is not one of the supported operations.
    """
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    writer = PdfWriter()

    if operation == "merge":
        for pdf_path in input_paths:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                writer.add_page(page)
    elif operation == "extract":
        reader = PdfReader(input_paths[0])
        for idx in (pages or []):
            writer.add_page(reader.pages[idx])
    elif operation == "rotate":
        reader = PdfReader(input_paths[0])
        for i, page in enumerate(reader.pages):
            if pages is None or i in pages:
                page.rotate(rotation or 90)
            writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    logger.info("PDF %s complete: %s", operation, output_path)
    return {"file_path": output_path}
