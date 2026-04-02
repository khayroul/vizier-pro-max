"""Tests for the repo doctor Hermes setup checks."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.bootstrap.doctor import run_doctor


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "hermes-agent").mkdir(parents=True)
    (root / ".gitmodules").write_text(
        '[submodule "hermes-agent"]\n'
        "\tpath = hermes-agent\n"
        "\turl = git@github.com:khayroul/hermes-agent.git\n"
        "\tbranch = vizier-gate2-patch\n",
        encoding="utf-8",
    )
    return root


def test_run_doctor_reports_healthy_setup(
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
) -> None:
    def fake_run_git(args: list[str], cwd: Path) -> str:
        if args[:3] == ["submodule", "status", "--"]:
            return " dd3c56aa5e8f6fc6d726fa94a379ff0e46b3fd1a hermes-agent"
        if args == ["rev-parse", "HEAD"]:
            return "dd3c56aa5e8f6fc6d726fa94a379ff0e46b3fd1a"
        if args == ["remote", "get-url", "origin"]:
            return "git@github.com:khayroul/hermes-agent.git"
        if args == ["remote", "get-url", "upstream"]:
            return "git@github.com:NousResearch/hermes-agent.git"
        if args == ["branch", "--show-current"]:
            return ""
        raise AssertionError(f"Unexpected git args: {args}")

    class DummyRegistry:
        def register(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr("scripts.bootstrap.doctor._run_git", fake_run_git)
    monkeypatch.setattr(
        "scripts.bootstrap.doctor.load_hermes_registry",
        lambda _root: DummyRegistry(),
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._detect_repo_python",
        lambda _root: project_root / ".venv" / "bin" / "python",
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._run_pip_check",
        lambda _python, _cwd: (True, "No dependency conflicts detected"),
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._probe_shared_imports",
        lambda _python, _root: {
            "hermes_cli.main": "ok",
            "gateway.run": "ok",
            "model_tools": "ok",
        },
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._probe_plugin_loads",
        lambda _python, _hermes: [
            {"name": "vizier_tools", "enabled": True, "error": None},
            {"name": "prompt_logger", "enabled": True, "error": None},
        ],
    )

    report = run_doctor(project_root)
    assert report.has_failures is False
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["origin_remote"] == "ok"
    assert statuses["upstream_remote"] == "ok"
    assert statuses["registry_loadable"] == "ok"
    assert statuses["dependency_conflicts"] == "ok"
    assert statuses["shared_runtime_imports"] == "ok"
    assert statuses["plugin_runtime"] == "ok"


def test_run_doctor_reports_missing_upstream_remote(
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
) -> None:
    def fake_run_git(args: list[str], cwd: Path) -> str:
        if args[:3] == ["submodule", "status", "--"]:
            return " dd3c56aa5e8f6fc6d726fa94a379ff0e46b3fd1a hermes-agent"
        if args == ["rev-parse", "HEAD"]:
            return "dd3c56aa5e8f6fc6d726fa94a379ff0e46b3fd1a"
        if args == ["remote", "get-url", "origin"]:
            return "git@github.com:khayroul/hermes-agent.git"
        if args == ["remote", "get-url", "upstream"]:
            raise RuntimeError("No such remote 'upstream'")
        if args == ["branch", "--show-current"]:
            return "vizier-gate2-patch"
        raise AssertionError(f"Unexpected git args: {args}")

    class DummyRegistry:
        def register(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr("scripts.bootstrap.doctor._run_git", fake_run_git)
    monkeypatch.setattr(
        "scripts.bootstrap.doctor.load_hermes_registry",
        lambda _root: DummyRegistry(),
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._detect_repo_python",
        lambda _root: project_root / ".venv" / "bin" / "python",
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._run_pip_check",
        lambda _python, _cwd: (True, "No dependency conflicts detected"),
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._probe_shared_imports",
        lambda _python, _root: {
            "hermes_cli.main": "ok",
            "gateway.run": "ok",
            "model_tools": "ok",
        },
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._probe_plugin_loads",
        lambda _python, _hermes: [],
    )

    report = run_doctor(project_root)
    assert report.has_failures is True
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["upstream_remote"] == "fail"


def test_run_doctor_reports_missing_submodule(project_root: Path) -> None:
    hermes_path = project_root / "hermes-agent"
    hermes_path.rmdir()

    report = run_doctor(project_root)
    assert report.has_failures is True
    assert report.checks[0].name == "submodule_present"
    assert report.checks[0].status == "fail"


def test_run_doctor_reports_broken_plugin_runtime(
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
) -> None:
    def fake_run_git(args: list[str], cwd: Path) -> str:
        if args[:3] == ["submodule", "status", "--"]:
            return " dd3c56aa5e8f6fc6d726fa94a379ff0e46b3fd1a hermes-agent"
        if args == ["rev-parse", "HEAD"]:
            return "dd3c56aa5e8f6fc6d726fa94a379ff0e46b3fd1a"
        if args == ["remote", "get-url", "origin"]:
            return "git@github.com:khayroul/hermes-agent.git"
        if args == ["remote", "get-url", "upstream"]:
            return "git@github.com:NousResearch/hermes-agent.git"
        if args == ["branch", "--show-current"]:
            return "vizier-gate2-patch"
        raise AssertionError(f"Unexpected git args: {args}")

    class DummyRegistry:
        def register(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr("scripts.bootstrap.doctor._run_git", fake_run_git)
    monkeypatch.setattr(
        "scripts.bootstrap.doctor.load_hermes_registry",
        lambda _root: DummyRegistry(),
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._detect_repo_python",
        lambda _root: project_root / ".venv" / "bin" / "python",
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._run_pip_check",
        lambda _python, _cwd: (True, "No dependency conflicts detected"),
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._probe_shared_imports",
        lambda _python, _root: {
            "hermes_cli.main": "ok",
            "gateway.run": "ok",
            "model_tools": "ok",
        },
    )
    monkeypatch.setattr(
        "scripts.bootstrap.doctor._probe_plugin_loads",
        lambda _python, _hermes: [
            {"name": "langfuse_tracer", "enabled": False, "error": "No module named 'langfuse'"},
        ],
    )

    report = run_doctor(project_root)
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["plugin_runtime"] == "fail"
