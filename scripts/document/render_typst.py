"""Render markdown content to PDF via Typst.

Wraps the typst CLI: writes a .typ file from content, compiles to PDF.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_ALLOWED_OUTPUT_DIR = (Path(__file__).parent.parent.parent / "output").resolve()


def _is_output_path_allowed(resolved_path: Path) -> bool:
    """Check if an output path is within allowed directories.

    Allows the project output/ dir by default, plus any dirs listed in
    VIZIER_ALLOWED_ROOTS (colon-separated), used by tests with tmp dirs.
    """
    if resolved_path.is_relative_to(_ALLOWED_OUTPUT_DIR):
        return True
    extra = os.environ.get("VIZIER_ALLOWED_ROOTS", "")
    if extra:
        for root in extra.split(":"):
            if root and resolved_path.is_relative_to(Path(root).resolve()):
                return True
    return False


def render_to_pdf(
    content: str,
    output_path: str | None = None,
    title: str = "Document",
) -> dict[str, str]:
    """Render text content into a PDF via Typst.

    Creates a temporary .typ file with basic formatting, compiles it
    with the typst CLI, and returns the output path.

    Args:
        content: Text content to render (plain text or Typst markup).
        output_path: Where to write the PDF. If None, writes to output/ dir.
        title: Document title for the header.

    Returns:
        Dict with ``pdf_path`` on success, or ``error`` on failure.
    """
    typst_bin = shutil.which("typst")
    if typst_bin is None:
        return {"error": "typst CLI not found — install via 'brew install typst'"}

    # Sanitize title to prevent path traversal
    title = re.sub(r"[^a-zA-Z0-9 _-]", "", title)

    # Default output path
    if output_path is None:
        output_dir = Path(__file__).parent.parent.parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{title.replace(' ', '_').lower()}.pdf")

    # Verify output path stays within allowed directories
    resolved_output = Path(output_path).resolve()
    if not _is_output_path_allowed(resolved_output):
        return {"error": f"Output path escapes allowed directory: {output_path}"}

    # Write Typst source to temp file
    typst_source = _wrap_content_as_typst(content, title)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".typ", delete=False, encoding="utf-8"
    ) as typ_file:
        typ_file.write(typst_source)
        typ_path = typ_file.name

    try:
        result = subprocess.run(
            [typst_bin, "compile", typ_path, output_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning("typst compile failed: %s", result.stderr)
            return {"error": f"typst compile failed: {result.stderr.strip()}"}

        logger.info("PDF rendered: %s", output_path)
        return {"pdf_path": output_path}

    except subprocess.TimeoutExpired:
        return {"error": "typst compile timed out after 30s"}
    finally:
        Path(typ_path).unlink(missing_ok=True)


def _wrap_content_as_typst(content: str, title: str) -> str:
    """Wrap plain text content in minimal Typst formatting.

    Args:
        content: The text body.
        title: Document title.

    Returns:
        Typst markup string ready for compilation.
    """
    # Escape content that could be interpreted as Typst markup
    # For Gate 1, keep it simple — raw text with basic heading
    return f"""#set page(margin: 2cm)
#set text(font: "Linux Libertine", size: 11pt)

= {title}

{content}
"""
