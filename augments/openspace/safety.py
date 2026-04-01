"""Skill safety validation -- check before loading into Hermes."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_SKILL_SIZE = 50_000  # 50KB

_DANGEROUS_PATTERNS = [
    # Shell destruction
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*(?:bash|sh)", re.IGNORECASE),
    re.compile(r"wget\s+.*&&\s*(?:chmod|bash|sh)", re.IGNORECASE),
    # Python code execution
    re.compile(r"eval\s*\(", re.IGNORECASE),
    re.compile(r"exec\s*\(", re.IGNORECASE),
    re.compile(r"compile\s*\(", re.IGNORECASE),
    re.compile(r"os\.system\s*\(", re.IGNORECASE),
    re.compile(r"os\.popen\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.\w+\s*\(", re.IGNORECASE),
    # Dynamic import / attribute access (bypass vectors)
    re.compile(r"__import__\s*\(", re.IGNORECASE),
    re.compile(r"importlib\.", re.IGNORECASE),
    re.compile(r"globals\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"locals\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"getattr\s*\(", re.IGNORECASE),
    re.compile(r"setattr\s*\(", re.IGNORECASE),
    re.compile(r"delattr\s*\(", re.IGNORECASE),
    # Filesystem destruction
    re.compile(r"shutil\.rmtree\s*\(", re.IGNORECASE),
    re.compile(r"\.unlink\s*\(", re.IGNORECASE),
    # Network exfiltration
    re.compile(r"open\s*\(.*,\s*['\"]w", re.IGNORECASE),
    re.compile(r"socket\.", re.IGNORECASE),
]


@dataclass
class SafetyResult:
    """Result of a skill safety check."""

    is_safe: bool
    reason: str


def check_skill_safety(skill_dir: Path) -> SafetyResult:
    """Validate a skill directory before loading.

    Checks for:
    - Presence of SKILL.md
    - Content size within limits
    - Absence of dangerous shell/code patterns
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return SafetyResult(is_safe=False, reason="Missing SKILL.md")

    content = skill_md.read_text()

    # Size check
    if len(content) > MAX_SKILL_SIZE:
        return SafetyResult(
            is_safe=False,
            reason=f"Size exceeds limit: {len(content)} > {MAX_SKILL_SIZE}",
        )

    # Dangerous pattern check
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(content):
            return SafetyResult(
                is_safe=False,
                reason=f"Shell injection risk: matched pattern '{pattern.pattern}'",
            )

    return SafetyResult(is_safe=True, reason="Passed all checks")
