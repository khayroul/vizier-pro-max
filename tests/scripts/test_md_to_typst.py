"""Tests for scripts/document/md_to_typst.py."""
from __future__ import annotations

from scripts.document.md_to_typst import convert, run


class TestMdToTypst:
    def test_converts_headings(self) -> None:
        result = convert("# Heading\n## Subheading")
        assert "= Heading" in result
        assert "== Subheading" in result

    def test_converts_bold_and_italic(self) -> None:
        result = convert("**Bold** and *italic*")
        assert "*Bold*" in result
        assert "_italic_" in result

    def test_converts_lists(self) -> None:
        result = convert("- one\n1. two")
        assert "- one" in result
        assert "+ two" in result

    def test_escapes_hashtags_and_typst_specials(self) -> None:
        result = convert("Launch #AI @home")
        assert "\\#AI" in result
        assert "\\@home" in result

    def test_preserves_code_blocks(self) -> None:
        result = convert("```python\nprint('#hello')\n```")
        assert "```python" in result
        assert "print('#hello')" in result

    def test_run_wrapper_returns_dict(self) -> None:
        result = run(markdown_text="# Hello")
        assert result["typst_content"] == "= Hello"
