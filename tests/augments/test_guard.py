"""Tests for augments/sandbox/guard.py — AST-based code guard."""
from __future__ import annotations

import pytest

from augments.sandbox.guard import GuardResult, check


class TestBlockedPatterns:
    """Each dangerous pattern must be individually blocked."""

    def test_subprocess_import_blocked(self) -> None:
        result = check("import subprocess\nsubprocess.run(['ls'])")
        assert not result.allowed
        assert any("subprocess" in p for p in result.blocked_patterns)

    def test_subprocess_from_import_blocked(self) -> None:
        result = check("from subprocess import run\nrun(['ls'])")
        assert not result.allowed
        assert any("subprocess" in p for p in result.blocked_patterns)

    def test_os_system_blocked(self) -> None:
        result = check("import os\nos.system('ls')")
        assert not result.allowed
        assert any("os.system" in p for p in result.blocked_patterns)

    def test_os_popen_blocked(self) -> None:
        result = check("import os\nos.popen('ls')")
        assert not result.allowed
        assert any("os.popen" in p or "os.exec" in p or "os." in p for p in result.blocked_patterns)

    def test_os_execvp_blocked(self) -> None:
        result = check("import os\nos.execvp('ls', ['ls'])")
        assert not result.allowed

    def test_eval_blocked(self) -> None:
        result = check("eval('1+1')")
        assert not result.allowed
        assert any("eval" in p for p in result.blocked_patterns)

    def test_exec_blocked(self) -> None:
        result = check("exec('x = 1')")
        assert not result.allowed
        assert any("exec" in p for p in result.blocked_patterns)

    def test_openai_import_blocked(self) -> None:
        result = check("import openai")
        assert not result.allowed
        assert any("openai" in p for p in result.blocked_patterns)

    def test_openai_from_import_blocked(self) -> None:
        result = check("from openai import Client")
        assert not result.allowed
        assert any("openai" in p for p in result.blocked_patterns)

    def test_anthropic_import_blocked(self) -> None:
        result = check("import anthropic")
        assert not result.allowed
        assert any("anthropic" in p for p in result.blocked_patterns)

    def test_anthropic_from_import_blocked(self) -> None:
        result = check("from anthropic import Anthropic")
        assert not result.allowed
        assert any("anthropic" in p for p in result.blocked_patterns)

    def test_dunder_import_blocked(self) -> None:
        result = check('__import__("subprocess")')
        assert not result.allowed
        assert any("__import__" in p for p in result.blocked_patterns)

    def test_importlib_blocked(self) -> None:
        result = check("import importlib\nimportlib.import_module('os')")
        assert not result.allowed
        assert any("importlib" in p for p in result.blocked_patterns)

    def test_socket_import_blocked(self) -> None:
        result = check("import socket")
        assert not result.allowed
        assert any("socket" in p for p in result.blocked_patterns)

    def test_socket_from_import_blocked(self) -> None:
        result = check("from socket import create_connection")
        assert not result.allowed
        assert any("socket" in p for p in result.blocked_patterns)


class TestSafeCode:
    """Safe code should pass the guard."""

    def test_print_allowed(self) -> None:
        result = check("print('hello world')")
        assert result.allowed
        assert result.blocked_patterns == []

    def test_math_allowed(self) -> None:
        result = check("import math\nresult = math.sqrt(16)")
        assert result.allowed

    def test_json_allowed(self) -> None:
        result = check("import json\ndata = json.loads('{}')")
        assert result.allowed

    def test_pathlib_read_allowed(self) -> None:
        result = check("from pathlib import Path\np = Path('output/data.txt')\ntext = p.read_text()")
        assert result.allowed

    def test_complex_ast_safe(self) -> None:
        code = """
def process(items):
    results = [x * 2 for x in items if x > 0]
    nested = {k: [v + 1 for v in vals] for k, vals in items.items()}
    return results, nested
"""
        result = check(code)
        assert result.allowed

    def test_nested_functions_safe(self) -> None:
        code = """
def outer():
    def inner():
        return 42
    return inner()
"""
        result = check(code)
        assert result.allowed


class TestOpenFileCalls:
    """open() calls: allow output/ and tmp/, block others."""

    def test_open_output_dir_allowed(self) -> None:
        result = check("f = open('output/result.txt', 'w')")
        assert result.allowed

    def test_open_tmp_dir_allowed(self) -> None:
        result = check("f = open('tmp/scratch.txt', 'w')")
        assert result.allowed

    def test_open_etc_blocked(self) -> None:
        result = check("f = open('/etc/passwd', 'r')")
        assert not result.allowed
        assert any("open" in p for p in result.blocked_patterns)

    def test_open_home_blocked(self) -> None:
        result = check("f = open('/home/user/.ssh/id_rsa', 'r')")
        assert not result.allowed

    def test_open_relative_blocked(self) -> None:
        result = check("f = open('../../secrets.txt', 'r')")
        assert not result.allowed

    def test_open_no_args_blocked(self) -> None:
        """open() with no arguments should be blocked."""
        result = check("f = open()")
        assert not result.allowed
        assert any("no path" in p for p in result.blocked_patterns)

    def test_open_dynamic_path_blocked(self) -> None:
        """open() with a variable (non-literal) path should be blocked."""
        result = check("path = 'foo.txt'\nf = open(path, 'r')")
        assert not result.allowed
        assert any("dynamic" in p for p in result.blocked_patterns)

    def test_attribute_open_not_blocked(self) -> None:
        """Method-style .open() calls (e.g. pathlib) should not be blocked."""
        result = check("from pathlib import Path\np = Path('output/x.txt')\nfh = p.open('w')")
        assert result.allowed


class TestSyntaxErrors:
    """Unparseable code should be rejected."""

    def test_syntax_error_rejected(self) -> None:
        result = check("def foo(")
        assert not result.allowed
        assert "parse" in result.error_message.lower() or "syntax" in result.error_message.lower()


class TestGuardResultFields:
    """GuardResult has correct fields and is frozen."""

    def test_guard_result_frozen(self) -> None:
        result = GuardResult(allowed=True, blocked_patterns=[], error_message="")
        with pytest.raises(AttributeError):
            result.allowed = False  # type: ignore[misc]
