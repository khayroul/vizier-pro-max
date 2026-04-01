"""Pre-execution AST scan for blocked patterns in execute_code input.

Blocks: os.system, subprocess, eval/exec, LLM API imports, filesystem
writes outside output/ and tmp/.
Reuses pattern detection from augments/openspace/safety.py where applicable.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

_BLOCKED_MODULES = frozenset({"subprocess", "importlib", "socket", "openai", "anthropic"})

_BLOCKED_OS_ATTRS = frozenset({"system", "popen", "execl", "execle", "execlp",
                                "execlpe", "execv", "execve", "execvp", "execvpe"})

_BLOCKED_BUILTINS = frozenset({"eval", "exec", "__import__"})

_ALLOWED_OPEN_PREFIXES = ("output/", "tmp/")


@dataclass(frozen=True)
class GuardResult:
    """Result of an AST guard check."""

    allowed: bool
    blocked_patterns: list[str] = field(default_factory=list)
    error_message: str = ""


def check(code: str) -> GuardResult:
    """Parse code to AST and check for blocked patterns.

    Args:
        code: Python source code string to validate.

    Returns:
        GuardResult indicating whether execution is allowed.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return GuardResult(
            allowed=False,
            blocked_patterns=["SyntaxError"],
            error_message=f"Failed to parse code: {exc}",
        )

    blocked: list[str] = []

    for node in ast.walk(tree):
        _check_imports(node, blocked)
        _check_calls(node, blocked)

    if blocked:
        message = "Blocked: " + "; ".join(blocked) + " -- use atomic tools instead"
        logger.warning("guard_blocked", patterns=blocked, code_preview=code[:200])
        return GuardResult(allowed=False, blocked_patterns=blocked, error_message=message)

    return GuardResult(allowed=True, blocked_patterns=[], error_message="")


def _check_imports(node: ast.AST, blocked: list[str]) -> None:
    """Check import statements for blocked modules."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            module_root = alias.name.split(".")[0]
            if module_root in _BLOCKED_MODULES:
                blocked.append(f"import {alias.name}")

    elif isinstance(node, ast.ImportFrom):
        if node.module is not None:
            module_root = node.module.split(".")[0]
            if module_root in _BLOCKED_MODULES:
                blocked.append(f"from {node.module} import ...")


def _check_calls(node: ast.AST, blocked: list[str]) -> None:
    """Check function calls for blocked builtins and os.* calls."""
    if not isinstance(node, ast.Call):
        return

    func = node.func

    # Direct builtin calls: eval(), exec(), __import__()
    if isinstance(func, ast.Name) and func.id in _BLOCKED_BUILTINS:
        blocked.append(f"{func.id}() call")
        return

    # Attribute calls: os.system(), os.popen(), etc.
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            if func.value.id == "os" and func.attr in _BLOCKED_OS_ATTRS:
                blocked.append(f"os.{func.attr}() call")
                return

        # open() calls — best-effort path check
        if isinstance(func, ast.Attribute) and func.attr == "open":
            # Not a direct open() call, skip
            pass

    # Direct open() calls
    if isinstance(func, ast.Name) and func.id == "open":
        _check_open_call(node, blocked)


def _check_open_call(node: ast.Call, blocked: list[str]) -> None:
    """Check open() calls — allow output/ and tmp/ paths only."""
    if not node.args:
        blocked.append("open() call with no path argument")
        return

    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        path_str = first_arg.value
        if any(path_str.startswith(prefix) for prefix in _ALLOWED_OPEN_PREFIXES):
            return
        blocked.append(f"open({path_str!r}) -- only output/ and tmp/ allowed")
    else:
        # Dynamic path — cannot verify at AST time, block conservatively
        blocked.append("open() with dynamic path -- only output/ and tmp/ allowed")
