"""Template inventory checks for ported Ultimate assets."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestTemplateInventory:
    def test_visual_templates_exist(self) -> None:
        visual_dir = ROOT / "templates" / "visual"
        names = sorted(path.name for path in visual_dir.glob("*.html"))
        assert len(names) == 30
        assert "social-post.html" in names
        assert "bold-knockout-square.html" in names
        assert "editorial-split-square.html" in names
        assert "hero-bottom-text-square.html" in names
        assert (visual_dir / "stock-heroes.json").exists()

    def test_document_templates_exist(self) -> None:
        docs_dir = ROOT / "templates" / "documents"
        names = sorted(path.name for path in docs_dir.glob("*.html"))
        assert names == [
            "article.html",
            "ebook-chapter.html",
            "invoice.html",
            "one-pager.html",
            "proposal.html",
            "report.html",
        ]

    def test_typst_templates_exist(self) -> None:
        typst_dir = ROOT / "templates" / "typst"
        names = sorted(path.name for path in typst_dir.glob("*.typ"))
        assert names == ["ebook.typ", "long-report.typ"]
