"""4-phase memory consolidation: DECIDE -> GATHER -> CONSOLIDATE -> PRUNE.

Uses Qwen 3.5 9B via Ollama for smart consolidation.
Falls back to rule-based merging if Ollama is unreachable.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from augments.dreamskill.signals import extract_signals

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.5:9b"
CONSOLIDATION_COOLDOWN = 86400  # 24 hours in seconds
MAX_MEMORY_LINES = 200

_CONSOLIDATION_PROMPT = """\
System: You are a memory consolidation engine.
You receive new signals from recent agent sessions
and the current MEMORY.md content.
Your job: merge new signals into memory, resolve contradictions, and
compress verbose observations. Output ONLY valid markdown.

Rules:
- When a new signal contradicts an existing entry, the newer one wins.
  Mark the old entry as superseded: "(Updated YYYY-MM-DD, previously: X)"
- Compress verbose observations into single-line facts
- Detect implicit patterns: if 3+ signals suggest a preference not
  explicitly stated, add it with confidence: medium
- Never invent facts not supported by the signals
- Output max 50 lines of consolidated entries

Input format:
EXISTING MEMORY:
{memory_content}

NEW SIGNALS:
{signals_json}

Output format (markdown list):
- [YYYY-MM-DD] Fact. (source: session, confidence: high|medium)"""


def _phase_decide(memory_dir: Path) -> bool:
    """Phase 1: Check if consolidation should run."""
    last_dream = memory_dir / ".last-dream"
    if last_dream.exists():
        try:
            last_ts = float(last_dream.read_text().strip())
            if time.time() - last_ts < CONSOLIDATION_COOLDOWN:
                return False
        except ValueError:
            pass  # Corrupted timestamp -- proceed
    return True


def _phase_gather(db_path: Path) -> list[dict[str, Any]]:
    """Phase 2: Gather signals from structlog traces."""
    return extract_signals(db_path=db_path)


def _phase_consolidate_qwen(
    signals: list[dict[str, Any]],
    memory_content: str,
) -> str | None:
    """Phase 3: Call Qwen via Ollama for smart consolidation."""
    prompt = _CONSOLIDATION_PROMPT.format(
        memory_content=memory_content,
        signals_json=json.dumps(signals, indent=2),
    )
    try:
        resp = httpx.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 4096},
            },
            timeout=60.0,
        )
        if resp.status_code == 200:
            result = resp.json().get("response", "")
            # Validate: must contain markdown list items
            if result.strip().startswith("-"):
                return result
            logger.warning("Qwen returned non-list output, falling back to rule-based")
            return None
        logger.warning("Ollama returned status %d", resp.status_code)
        return None
    except Exception as exc:
        logger.warning("Ollama unreachable, falling back to rule-based: %s", exc)
        return None


def _phase_consolidate_fallback(
    signals: list[dict[str, Any]],
    memory_content: str,
) -> str:
    """Rule-based fallback consolidation (original dream-skill behavior)."""
    existing_lines = [
        line
        for line in memory_content.strip().splitlines()
        if line.strip()
    ]
    new_lines: list[str] = []
    for signal in signals:
        date = signal["date"]
        fact = signal["fact"]
        conf = signal["confidence"]
        line = f"- [{date}] {fact} (confidence: {conf})"
        new_lines.append(line)

    # Simple dedup: skip if fact already exists
    combined = existing_lines[:]
    existing_text = " ".join(existing_lines).lower()
    for line in new_lines:
        # Extract the fact portion for comparison
        fact_part = line.split("]", 1)[-1].strip() if "]" in line else line
        if fact_part.lower()[:50] not in existing_text:
            combined.append(line)

    return "\n".join(combined[:MAX_MEMORY_LINES]) + "\n"


def _phase_prune(memory_dir: Path, consolidated: str) -> None:
    """Phase 4: Write consolidated memory and update timestamp."""
    memory_file = memory_dir / "MEMORY.md"
    memory_file.write_text(consolidated)

    # Update timestamp
    last_dream = memory_dir / ".last-dream"
    last_dream.write_text(str(time.time()))


def consolidate(
    *,
    db_path: Path,
    memory_dir: Path,
) -> dict[str, str]:
    """Run the 4-phase consolidation cycle."""
    # Phase 1: DECIDE
    if not _phase_decide(memory_dir):
        return {"status": "skipped", "reason": "Too recent"}

    # Phase 2: GATHER
    signals = _phase_gather(db_path)
    if not signals:
        return {"status": "skipped", "reason": "No signals found"}

    # Read existing memory
    memory_file = memory_dir / "MEMORY.md"
    memory_content = memory_file.read_text() if memory_file.exists() else ""

    # Phase 3: CONSOLIDATE
    qwen_result = _phase_consolidate_qwen(signals, memory_content)
    if qwen_result is not None:
        consolidated = qwen_result
        status = "consolidated"
    else:
        consolidated = _phase_consolidate_fallback(signals, memory_content)
        status = "fallback"

    # Phase 4: PRUNE
    _phase_prune(memory_dir, consolidated)

    logger.info("Memory consolidation complete: %s", status)
    return {"status": status}
