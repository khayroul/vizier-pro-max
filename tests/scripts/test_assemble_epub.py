"""Tests for scripts/document/assemble_epub.py."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


class _FakeBook:
    def __init__(self) -> None:
        self.identifier = ""
        self.title = ""
        self.language = ""
        self.author = ""
        self.cover: tuple[str, bytes] | None = None
        self.items: list[object] = []
        self.toc: tuple[object, ...] = ()
        self.spine: list[object] = []

    def set_identifier(self, identifier: str) -> None:
        self.identifier = identifier

    def set_title(self, title: str) -> None:
        self.title = title

    def set_language(self, language: str) -> None:
        self.language = language

    def add_author(self, author: str) -> None:
        self.author = author

    def set_cover(self, name: str, content: bytes) -> None:
        self.cover = (name, content)

    def add_item(self, item: object) -> None:
        self.items.append(item)


class _FakeChapter:
    def __init__(self, *, title: str, file_name: str, lang: str) -> None:
        self.title = title
        self.file_name = file_name
        self.lang = lang
        self.content = ""


class _FakeEpubModule:
    last_written_path: str | None = None
    last_book: _FakeBook | None = None

    @staticmethod
    def EpubBook() -> _FakeBook:
        return _FakeBook()

    @staticmethod
    def EpubHtml(*, title: str, file_name: str, lang: str) -> _FakeChapter:
        return _FakeChapter(title=title, file_name=file_name, lang=lang)

    @staticmethod
    def EpubNcx() -> str:
        return "ncx"

    @staticmethod
    def EpubNav() -> str:
        return "nav"

    @staticmethod
    def write_epub(path: str, book: _FakeBook) -> None:
        _FakeEpubModule.last_written_path = path
        _FakeEpubModule.last_book = book
        Path(path).write_bytes(b"epub")


class TestAssembleEpub:
    def test_builds_epub(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setitem(sys.modules, "ebooklib", types.SimpleNamespace(epub=_FakeEpubModule))

        from scripts.document.assemble_epub import run

        output = tmp_path / "book.epub"
        result = run(
            title="My Book",
            author="Vizier",
            chapters=[{"title": "Intro", "html": "<p>Hello</p>"}],
            output_path=str(output),
        )

        assert result["file_path"] == str(output)
        assert output.exists()
        assert _FakeEpubModule.last_book is not None
        assert _FakeEpubModule.last_book.title == "My Book"
        assert len(_FakeEpubModule.last_book.items) >= 3

    def test_adds_cover_when_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setitem(sys.modules, "ebooklib", types.SimpleNamespace(epub=_FakeEpubModule))

        from scripts.document.assemble_epub import run

        cover = tmp_path / "cover.png"
        cover.write_bytes(b"png")
        run(
            title="My Book",
            author="Vizier",
            chapters=[],
            cover_path=str(cover),
            output_path=str(tmp_path / "book.epub"),
        )

        assert _FakeEpubModule.last_book is not None
        assert _FakeEpubModule.last_book.cover == ("cover.png", b"png")

    def test_requires_title(self, tmp_path: Path) -> None:
        from scripts.document.assemble_epub import run

        with pytest.raises(ValueError, match="title is required"):
            run(title="", author="Vizier", chapters=[], output_path=str(tmp_path / "book.epub"))
