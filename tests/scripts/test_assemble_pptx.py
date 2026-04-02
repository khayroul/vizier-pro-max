"""Tests for scripts/document/assemble_pptx.py."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


class _FakeTitle:
    def __init__(self) -> None:
        self.text = ""


class _FakePlaceholder:
    def __init__(self) -> None:
        self.text = ""


class _FakeNotesFrame:
    def __init__(self) -> None:
        self.text = ""


class _FakeNotesSlide:
    def __init__(self) -> None:
        self.notes_text_frame = _FakeNotesFrame()


class _FakeShapes:
    def __init__(self) -> None:
        self.title = _FakeTitle()
        self.pictures: list[tuple[str, object, object, object]] = []

    def add_picture(self, path: str, left: object, top: object, width: object) -> None:
        self.pictures.append((path, left, top, width))


class _FakeSlide:
    def __init__(self) -> None:
        self.shapes = _FakeShapes()
        self.placeholders = {1: _FakePlaceholder()}
        self.notes_slide = _FakeNotesSlide()


class _FakeSlides:
    def __init__(self) -> None:
        self._slides: list[_FakeSlide] = []

    def add_slide(self, _layout: object) -> _FakeSlide:
        slide = _FakeSlide()
        self._slides.append(slide)
        return slide


class _FakeCoreProperties:
    def __init__(self) -> None:
        self.title = ""


class _FakePresentation:
    last_saved_path: str | None = None
    last_instance: "_FakePresentation | None" = None

    def __init__(self) -> None:
        self.core_properties = _FakeCoreProperties()
        self.slide_layouts = [object(), object()]
        self.slides = _FakeSlides()
        _FakePresentation.last_instance = self

    def save(self, path: str) -> None:
        _FakePresentation.last_saved_path = path
        Path(path).write_bytes(b"pptx")


class TestAssemblePptx:
    def test_builds_slide_deck(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setitem(sys.modules, "pptx", types.SimpleNamespace(Presentation=_FakePresentation))
        monkeypatch.setitem(sys.modules, "pptx.util", types.SimpleNamespace(Inches=lambda value: value))

        from scripts.document.assemble_pptx import run

        output = tmp_path / "deck.pptx"
        result = run(
            title="Deck",
            slides=[{"title": "Intro", "body": "Welcome", "notes": "Speak clearly"}],
            output_path=str(output),
        )

        assert result["file_path"] == str(output)
        assert output.exists()
        assert _FakePresentation.last_instance is not None
        assert _FakePresentation.last_instance.core_properties.title == "Deck"
        slide = _FakePresentation.last_instance.slides._slides[0]
        assert slide.shapes.title.text == "Intro"
        assert slide.placeholders[1].text == "Welcome"
        assert slide.notes_slide.notes_text_frame.text == "Speak clearly"

    def test_adds_image_when_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setitem(sys.modules, "pptx", types.SimpleNamespace(Presentation=_FakePresentation))
        monkeypatch.setitem(sys.modules, "pptx.util", types.SimpleNamespace(Inches=lambda value: value))

        from scripts.document.assemble_pptx import run

        image = tmp_path / "image.png"
        image.write_bytes(b"png")

        run(
            title="Deck",
            slides=[{"title": "Intro", "image_path": str(image)}],
            output_path=str(tmp_path / "deck.pptx"),
        )

        slide = _FakePresentation.last_instance.slides._slides[0]  # type: ignore[union-attr]
        assert slide.shapes.pictures[0][0] == str(image)

    def test_requires_output_path(self) -> None:
        from scripts.document.assemble_pptx import run

        with pytest.raises(ValueError, match="output_path is required"):
            run(title="Deck", slides=[], output_path="")
