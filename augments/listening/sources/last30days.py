"""last30days subprocess adapter."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import ClassVar

import structlog

from augments.listening.watchlist import ListeningItem

logger = structlog.get_logger(__name__)

_DEFAULT_SCRIPT_PATH = (
    Path.home()
    / ".claude/plugins/cache/superpowers-marketplace"
    / "superpowers/5.0.2/skills/last30days/scripts/last30days.py"
)


class Last30DaysAdapter:
    name: ClassVar[str] = "last30days"

    def __init__(self, script_path: Path | None = None) -> None:
        self._script_path = script_path or Path(
            os.environ.get("LAST30DAYS_SCRIPT_PATH", str(_DEFAULT_SCRIPT_PATH))
        )

    def available(self) -> bool:
        return self._script_path.exists() and bool(os.environ.get("SCRAPECREATORS_API_KEY"))

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
        sources: list[str] | None = None,
    ) -> list[ListeningItem]:
        all_items: list[ListeningItem] = []
        source_arg = ",".join(sources) if sources else ""
        for keyword in keywords:
            cmd = [
                "python3",
                str(self._script_path),
                keyword,
                "--emit=json",
                f"--limit={limit}",
                f"--geo={geo}",
                f"--language={language}",
            ]
            if source_arg:
                cmd.append(f"--sources={source_arg}")
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={**os.environ},
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning("last30days execution failed", keyword=keyword, error=str(exc))
                continue
            if result.returncode != 0:
                logger.warning("last30days returned non-zero", keyword=keyword, code=result.returncode)
                continue
            all_items.extend(_parse_output(result.stdout))
        return all_items


def _parse_output(raw: str) -> list[ListeningItem]:
    """Parse last30days JSON output."""
    try:
        payload = json.loads(raw.strip())
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    items = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        items.append(
            ListeningItem(
                source=str(entry.get("source", "unknown")),
                url=str(entry.get("url")) if entry.get("url") else None,
                title=str(entry.get("title", "")),
                snippet=str(entry.get("snippet", "")),
                score=float(entry.get("score", 0.0)),
                engagement=int(entry.get("engagement", 0)),
                published_at=str(entry.get("published_at")) if entry.get("published_at") else None,
            )
        )
    return items
