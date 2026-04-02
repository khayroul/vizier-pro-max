"""Convert a markdown-like document body to simple Typst markup."""
from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

_SPECIALS_RE = re.compile(r"([@$<>{}])")


def _escape_text(text: str) -> str:
    """Escape Typst-special characters while keeping heading markers intact."""
    return _SPECIALS_RE.sub(r"\\\1", text)


def convert(markdown_text: str) -> str:
    """Convert markdown text to lightweight Typst markup."""
    lines: list[str] = []
    in_code_block = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            language = stripped.removeprefix("```").strip()
            fence = f"```{language}" if language else "```"
            lines.append(fence)
            in_code_block = not in_code_block
            continue

        if in_code_block:
            lines.append(line)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = "=" * len(heading_match.group(1))
            lines.append(f"{level} {_escape_text(heading_match.group(2))}")
            continue

        processed = _escape_text(line)
        processed = re.sub(r"\*\*(.+?)\*\*", r"<<BOLD>>\1<</BOLD>>", processed)
        processed = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", processed)
        processed = processed.replace("<<BOLD>>", "*").replace("<</BOLD>>", "*")
        processed = re.sub(r"^[-*]\s+", "- ", processed)
        processed = re.sub(r"^\d+\.\s+", "+ ", processed)
        processed = re.sub(r"#(\w)", r"\\#\1", processed)
        lines.append(processed)

    result = "\n".join(lines).strip()
    logger.debug("Converted markdown to typst", input_length=len(markdown_text), output_length=len(result))
    return result


def run(*, markdown_text: str) -> dict[str, str]:
    """Tool-style wrapper around markdown to Typst conversion."""
    return {"typst_content": convert(markdown_text)}
