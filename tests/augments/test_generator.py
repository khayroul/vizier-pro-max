"""Tests for OpenSpace generator -- SKILL.md + pipeline draft creation."""
from __future__ import annotations

from pathlib import Path

from augments.openspace.generator import generate_pipeline_draft, generate_skill_md


class TestGenerator:
    def test_generate_skill_md(self, tmp_path: Path) -> None:
        chain = {
            "tools": ["httpx_fetch", "jinja2_render", "playwright_screenshot"],
            "occurrences": 6,
            "description": "Fetch URL, render template, take screenshot",
        }
        skill_path = generate_skill_md(chain=chain, output_dir=tmp_path)
        assert skill_path.exists()
        content = skill_path.read_text()
        assert "httpx_fetch" in content
        assert "jinja2_render" in content

    def test_generate_pipeline_draft(self, tmp_path: Path) -> None:
        chain = {
            "tools": ["httpx_fetch", "jinja2_render", "playwright_screenshot"],
            "occurrences": 6,
            "description": "Fetch -> render -> screenshot",
        }
        draft_path = generate_pipeline_draft(chain=chain, output_dir=tmp_path)
        assert draft_path.exists()
        content = draft_path.read_text()
        assert "def run(" in content
        assert "httpx_fetch" in content or "fetch" in content.lower()
