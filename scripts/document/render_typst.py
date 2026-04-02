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
    accent_color: str = "2563eb",
    hashtags: list[str] | None = None,
) -> dict[str, str]:
    """Render text content into a PDF via Typst.

    Creates a temporary .typ file with branded formatting, compiles it
    with the typst CLI, and returns the output path.

    Args:
        content: Text content to render (plain text or Typst markup).
        output_path: Where to write the PDF. If None, writes to output/ dir.
        title: Document title for the header.
        accent_color: Hex color for accent bars and title (without #).
        hashtags: Optional list of hashtags to append at document end.

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
    typst_source = _wrap_content_as_typst(content, title, accent_color, hashtags)

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


def _markdown_to_typst(content: str) -> str:
    """Convert common markdown formatting to Typst equivalents.

    Handles headings, bold, italic, hashtags, and code blocks so that
    LLM-generated markdown compiles cleanly in Typst.
    """
    lines: list[str] = []
    in_code_block = False
    for line in content.splitlines():
        # Toggle code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                lines.append("```")
                in_code_block = False
            else:
                lang = line.strip().removeprefix("```").strip()
                lines.append(f"```{lang}" if lang else "```")
                in_code_block = True
            continue

        if in_code_block:
            lines.append(line)
            continue

        # Markdown headings -> Typst headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = "=" * len(heading_match.group(1))
            lines.append(f"{level} {heading_match.group(2)}")
            continue

        # Escape standalone # (hashtags like #AI) that aren't headings
        processed = re.sub(r"#(\w)", r"\#\1", line)
        # Markdown bold **text** -> Typst *text*
        processed = re.sub(r"\*\*(.+?)\*\*", r"*\1*", processed)
        lines.append(processed)

    return "\n".join(lines)


def _wrap_content_as_typst(
    content: str,
    title: str,
    accent_color: str = "2563eb",
    hashtags: list[str] | None = None,
) -> str:
    """Wrap content in branded Typst formatting with accent bars.

    Args:
        content: The text body (markdown supported).
        title: Document title displayed as large heading.
        accent_color: Hex color for accent bars and title text (without #).
        hashtags: Optional list of hashtags to render at document end.

    Returns:
        Typst markup string ready for compilation.
    """
    typst_content = _markdown_to_typst(content)
    hashtag_block = ""
    if hashtags:
        escaped = " ".join(f"\\#{tag.lstrip('#')}" for tag in hashtags)
        hashtag_block = (
            f'\n#v(1.5em)\n#text(size: 10pt, fill: luma(120))[{escaped}]\n'
        )

    return f"""#set page(
  paper: "a5",
  flipped: true,
  margin: (top: 2.5cm, bottom: 2cm, left: 2cm, right: 2cm),
)
#set text(size: 12pt)
#set par(justify: true, leading: 1.4em, spacing: 1.2em)

#rect(width: 100%, height: 6pt, fill: rgb("{accent_color}"))

#v(0.8em)

#text(size: 22pt, weight: "bold", fill: rgb("{accent_color}"))[{title}]

#v(0.3em)

#line(length: 40%, stroke: 0.5pt + luma(180))

#v(0.8em)

{typst_content}
{hashtag_block}
#v(1fr)

#rect(width: 100%, height: 6pt, fill: rgb("{accent_color}"))
"""
