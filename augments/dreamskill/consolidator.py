"""Structured observational-memory consolidation for derived MEMORY.md."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from augments.observational.compiler import write_memory_markdown
from augments.observational.extractor import sync_build_capture_to_ledger
from augments.observational.ledger import ObservationalLedger
from augments.observational.reflector import reflect_observations

logger = logging.getLogger(__name__)

CONSOLIDATION_COOLDOWN = 86400  # 24 hours in seconds


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


def _phase_prune(memory_dir: Path, consolidated: str) -> None:
    """Write derived memory and update the cooldown timestamp."""
    memory_file = memory_dir / "MEMORY.md"
    memory_file.write_text(consolidated, encoding="utf-8")

    last_dream = memory_dir / ".last-dream"
    last_dream.write_text(str(time.time()), encoding="utf-8")


def consolidate(
    *,
    db_path: Path,
    memory_dir: Path,
    state_root: Path | None = None,
) -> dict[str, str]:
    """Consolidate structured observational memory into derived MEMORY.md."""

    if not _phase_decide(memory_dir):
        return {"status": "skipped", "reason": "Too recent"}

    resolved_state_root = state_root or (db_path.parent / "state")
    ledger = ObservationalLedger(state_root=resolved_state_root)
    episodes, _observations = sync_build_capture_to_ledger(
        ledger=ledger,
        state_root=resolved_state_root,
    )
    if not episodes:
        return {"status": "skipped", "reason": "No captured evidence found"}

    active_observations = ledger.list_observations(status="active")
    if not active_observations:
        return {"status": "skipped", "reason": "No observations derived"}

    reflected = reflect_observations(
        active_observations,
        existing_reflections=ledger.list_reflections(),
    )
    for reflection in reflected:
        ledger.save_reflection(reflection)

    consolidated = write_memory_markdown(
        memory_path=memory_dir / "MEMORY.md",
        observations=ledger.list_observations(status="active"),
        reflections=ledger.list_reflections(status="active"),
    )
    _phase_prune(memory_dir, consolidated)

    logger.info("Memory consolidation complete: consolidated")
    return {"status": "consolidated"}
