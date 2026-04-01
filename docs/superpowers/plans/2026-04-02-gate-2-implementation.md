# Vizier Pro-Max Gate 2 Implementation Plan — "Works While I Sleep"

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hermes running as Vizier with mid-session toolset switching, all workflow toolsets, parallel + unattended sessions, OpenSpace skill evolution, dream-skill memory consolidation, template cloning, quality gates 3-6, and Telegram/WhatsApp delivery.

**Architecture:** Generic agent-level tool extension in Hermes (18-line patch) enables `switch_toolset`. YAML manifests + scripts add 9 new tools across 4 workflow toolsets. DeerFlow patterns wrap `delegate_task` batch mode for parallel sessions. Hermes cron scheduler runs unattended jobs. OpenSpace (MCP server) evolves skills from structlog traces. Dream-skill (Qwen 3.5 9B) consolidates memory on session end. Template cloning converges vision → HTML via multi-signal delta loop. Quality gate extends to 6 layers.

**Tech Stack:** Python 3.11+, Hermes Agent v0.6.0, playwright, pandas, matplotlib, edge-tts, scikit-image, pixelmatch, opencv-python-headless, pytesseract, lingua-py, FastMCP, Qwen 3.5 9B (Ollama)

**Spec:** `docs/superpowers/specs/2026-04-02-gate-2-design.md`

**Gate 1 plan (format reference):** `docs/superpowers/plans/2026-04-01-gate-1-implementation.md`

**Hermes internals:**
- `~/hermes-agent/run_agent.py` — AIAgent, `_invoke_tool` (line 5268), main loop (line 6302+)
- `~/hermes-agent/tools/registry.py` — `registry.register(name, toolset, schema, handler, check_fn, ...)`
- `~/hermes-agent/hermes_cli/plugins.py` — `VALID_HOOKS`, `PluginContext.register_tool()`, `register_hook()`
- `~/hermes-agent/tools/delegate_tool.py` — `delegate_task`, batch mode via `ThreadPoolExecutor`
- `~/hermes-agent/cron/scheduler.py` — `run_job()`, `tick()`

**Shared constant (create early, reference everywhere):**

```python
# config/toolsets.py — single source of truth for vizier toolset names
VIZIER_WORKFLOW_TOOLSETS = frozenset({
    "vizier-content", "vizier-document", "vizier-visual",
    "vizier-research", "vizier-audio", "vizier-delivery",
    "vizier-fallback",
})
```

---

## File Map

### Chunk 1 — Hermes Patch + switch_toolset

| File | Responsibility |
|------|---------------|
| `~/hermes-agent/hermes_cli/plugins.py` | Add `"on_agent_ready"` to VALID_HOOKS |
| `~/hermes-agent/run_agent.py` | Add `_custom_agent_tools`, `_pending_toolsets_rebuild`, elif dispatch, main loop rebuild |
| `config/toolsets.py` | Shared constant: VIZIER_WORKFLOW_TOOLSETS |
| `plugins/switch_toolset.py` | Hermes plugin: register switch_toolset schema + agent-level handler |
| `tests/plugins/test_switch_toolset.py` | Unit tests for handler + edge cases |
| `tests/test_integration_chunk1.py` | E2E: toolset switch mid-session |

### Chunk 2 — Workflow Toolsets

| File | Responsibility |
|------|---------------|
| `manifests/visual/playwright_screenshot.yaml` | HTML → PNG screenshot |
| `manifests/visual/pillow_process.yaml` | Image manipulation |
| `manifests/visual/fal_generate.yaml` | AI image generation |
| `manifests/research/pandas_analyze.yaml` | Data analysis |
| `manifests/research/matplotlib_chart.yaml` | Chart generation |
| `manifests/audio/ffmpeg_process.yaml` | Audio/video processing |
| `manifests/audio/edge_tts_speak.yaml` | Text-to-speech |
| `manifests/document/pandoc_convert.yaml` | Format conversion |
| `manifests/document/pypdf_merge.yaml` | PDF merge/split |
| `scripts/visual/screenshot_html.py` | Playwright wrapper |
| `scripts/visual/process_image.py` | Pillow wrapper |
| `scripts/visual/generate_image.py` | fal.ai httpx client |
| `scripts/research/analyze_data.py` | Pandas operations |
| `scripts/research/render_chart.py` | Matplotlib wrapper |
| `scripts/audio/process_media.py` | ffmpeg CLI wrapper |
| `scripts/audio/speak_text.py` | edge-tts wrapper |
| `scripts/document/convert_format.py` | Pandoc CLI wrapper |
| `scripts/document/merge_pdfs.py` | pypdf operations |
| `pipelines/clone_converge.py` | Template cloning stub (Chunk 4 replaces) |
| `pipelines/poster_batch.py` | Batch poster stub |
| `pipelines/competitive_analysis.py` | Research pipeline stub |
| `pipelines/tts_generate.py` | TTS pipeline stub |

### Chunk 3 — Sessions + Channels

| File | Responsibility |
|------|---------------|
| `augments/deerflow/task_decomposer.py` | Complex task → sub-task specs for delegate_task batch |
| `augments/deerflow/result_synthesizer.py` | Merge child results into deliverable |
| `augments/deerflow/shared_memory.py` | Debounced cross-agent observation queue |
| `plugins/deerflow_orchestration.py` | Register decompose_task + merge_results as agent-level tools |
| `middleware/cron_guard.py` | Safety layer for unattended sessions |
| `bridge/cron_loader.py` | Load cron YAML configs, register with Hermes scheduler |
| `config/cron/content_calendar.yaml` | Daily social post generation |
| `config/cron/quality_review.yaml` | Weekly quality audit |
| `config/cron/health_check.yaml` | Daily system status |
| `manifests/delivery/send_telegram.yaml` | Telegram delivery |
| `manifests/delivery/send_whatsapp.yaml` | WhatsApp delivery |
| `scripts/delivery/send_telegram.py` | python-telegram-bot wrapper |
| `scripts/delivery/send_whatsapp.py` | WhatsApp Business API client |

### Chunk 4 — Augments + Quality Gates

| File | Responsibility |
|------|---------------|
| `augments/openspace/capturer.py` | Detect repeating tool chains from structlog |
| `augments/openspace/generator.py` | Generate SKILL.md + pipeline draft from captured chain |
| `augments/openspace/fixer.py` | Auto-repair broken skills from error logs |
| `augments/openspace/deriver.py` | Promote better skill variants |
| `augments/openspace/version_dag.py` | SQLite store for skill lineage |
| `augments/openspace/safety.py` | Skill safety validation |
| `augments/openspace/pruner.py` | Archive stale skills |
| `augments/openspace/server.py` | FastMCP server (4 tools) |
| `augments/dreamskill/consolidator.py` | 4-phase memory consolidation |
| `augments/dreamskill/signals.py` | Signal extraction from structlog |
| `augments/dreamskill/pruner.py` | MEMORY.md size management |
| `pipelines/clone_converge.py` | Template cloning loop (replaces stub) |
| `scripts/visual/calculate_delta.py` | Multi-signal image comparison |
| `scripts/visual/parameterize_template.py` | Jinja2 placeholder injection |
| `middleware/quality_gate.py` | Extend with layers 3-6 |
| `config/openspace.yaml` | OpenSpace thresholds + config |

### Test Files

| Test file | Tests for |
|-----------|-----------|
| `tests/plugins/test_switch_toolset.py` | switch_toolset handler, edge cases |
| `tests/test_integration_chunk1.py` | E2E toolset switching |
| `tests/scripts/test_screenshot_html.py` | Playwright wrapper |
| `tests/scripts/test_process_image.py` | Pillow operations |
| `tests/scripts/test_generate_image.py` | fal.ai client |
| `tests/scripts/test_analyze_data.py` | Pandas operations |
| `tests/scripts/test_render_chart.py` | Matplotlib wrapper |
| `tests/scripts/test_process_media.py` | ffmpeg wrapper |
| `tests/scripts/test_speak_text.py` | edge-tts wrapper |
| `tests/scripts/test_convert_format.py` | Pandoc wrapper |
| `tests/scripts/test_merge_pdfs.py` | pypdf operations |
| `tests/pipelines/test_clone_converge.py` | Template cloning |
| `tests/pipelines/test_poster_batch.py` | Batch poster |
| `tests/pipelines/test_competitive_analysis.py` | Research pipeline |
| `tests/pipelines/test_tts_generate.py` | TTS pipeline |
| `tests/test_integration_chunk2.py` | E2E: manifest load → tool exec |
| `tests/augments/test_task_decomposer.py` | Task decomposition |
| `tests/augments/test_result_synthesizer.py` | Result merging |
| `tests/augments/test_shared_memory.py` | Debounced queue |
| `tests/middleware/test_cron_guard.py` | Safety checks |
| `tests/bridge/test_cron_loader.py` | Cron YAML loading |
| `tests/scripts/test_send_telegram.py` | Telegram delivery |
| `tests/scripts/test_send_whatsapp.py` | WhatsApp delivery |
| `tests/test_integration_chunk3.py` | E2E: decompose → delegate → merge |
| `tests/augments/test_capturer.py` | Pattern detection |
| `tests/augments/test_generator.py` | Skill/pipeline generation |
| `tests/augments/test_fixer.py` | Skill repair |
| `tests/augments/test_deriver.py` | Variant promotion |
| `tests/augments/test_version_dag.py` | SQLite lineage store |
| `tests/augments/test_safety.py` | Safety validation |
| `tests/augments/test_consolidator.py` | 4-phase consolidation |
| `tests/augments/test_signals.py` | Signal extraction |
| `tests/scripts/test_calculate_delta.py` | Delta calculator |
| `tests/scripts/test_parameterize_template.py` | Template parameterizer |
| `tests/middleware/test_quality_gate_extended.py` | Layers 3-6 |
| `tests/pipelines/test_clone_converge_full.py` | Full convergence loop |
| `tests/test_integration_chunk4.py` | E2E: capture → evolve → quality gate |

---

## Chunk 1: Hermes Patch + switch_toolset

### Task 1: Shared toolset constant + package scaffolding

**Files:**
- Create: `config/__init__.py`, `config/toolsets.py`
- Create: `augments/__init__.py`, `augments/deerflow/__init__.py`, `augments/openspace/__init__.py`, `augments/dreamskill/__init__.py`
- Create: `scripts/visual/__init__.py`, `scripts/research/__init__.py`, `scripts/audio/__init__.py`, `scripts/document/__init__.py`, `scripts/delivery/__init__.py`
- Create: `tests/augments/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create config/toolsets.py — single source of truth**

```python
"""Vizier toolset constants — single source of truth."""
from __future__ import annotations

VIZIER_WORKFLOW_TOOLSETS = frozenset({
    "vizier-content",
    "vizier-document",
    "vizier-visual",
    "vizier-research",
    "vizier-audio",
    "vizier-delivery",
    "vizier-fallback",
    # vizier-code and vizier-knowledge deferred to Gate 3
})
```

- [ ] **Step 2: Create all __init__.py files for new packages**

All `__init__.py` files are empty docstrings:

```python
# config/__init__.py
"""Vizier configuration."""
```

```python
# augments/__init__.py
"""Absorbed agentic components (nervous system)."""
```

```python
# augments/deerflow/__init__.py
"""DeerFlow sub-agent coordination patterns."""
```

```python
# augments/openspace/__init__.py
"""OpenSpace skill evolution engine."""
```

```python
# augments/dreamskill/__init__.py
"""Dream-skill memory consolidation."""
```

Script directories get empty `__init__.py` (no docstring needed).

- [ ] **Step 3: Update pyproject.toml — add augments, new deps**

```toml
# Add to [project] dependencies:
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "structlog>=24.0",
    "httpx>=0.27",
    "jinja2>=3.1",
    "pypdf>=4.0",
    "pillow>=10.0",
    "python-telegram-bot>=22.0",
    "playwright>=1.40,<2",
    "pandas>=2.0,<3",
    "matplotlib>=3.8,<4",
    "edge-tts>=6.1,<7",
    "scikit-image>=0.22,<1",
    "pixelmatch>=0.3,<1",
    "opencv-python-headless>=4.9,<5",
    "pytesseract>=0.3,<1",
    "lingua-py>=2.0,<3",
    "mcp>=1.0,<2",
]

# Update [tool.setuptools.packages.find]:
include = ["adapter*", "tools*", "plugins*", "pipelines*", "middleware*", "bridge*", "augments*", "config*"]
```

- [ ] **Step 4: Install new deps + system tools**

Run:
```bash
cd ~/vizier-pro-max && pip install -e ".[dev]"
python -m playwright install chromium
brew install ffmpeg pandoc tesseract
brew install tesseract-lang
```

- [ ] **Step 5: Commit**

```bash
git add config/ augments/ scripts/visual/ scripts/research/ scripts/audio/ scripts/document/ scripts/delivery/ tests/augments/ pyproject.toml
git commit -m "chore: Gate 2 scaffold — new packages, deps, shared toolset constant"
```

---

### Task 2: Hermes patch — on_agent_ready hook + generic extension point

**Files:**
- Modify: `~/hermes-agent/hermes_cli/plugins.py`
- Modify: `~/hermes-agent/run_agent.py`

- [ ] **Step 1: Add on_agent_ready to VALID_HOOKS**

In `~/hermes-agent/hermes_cli/plugins.py`, line 52, add `"on_agent_ready"` to the set:

```python
VALID_HOOKS: Set[str] = {
    "pre_tool_call",
    "post_tool_call",
    "pre_llm_call",
    "post_llm_call",
    "on_session_start",
    "on_session_end",
    "on_agent_ready",
}
```

- [ ] **Step 2: Add _custom_agent_tools and _pending_toolsets_rebuild to AIAgent.__init__**

In `~/hermes-agent/run_agent.py`, after `self.enabled_toolsets = enabled_toolsets` (line ~652), add:

```python
        # Gate 2: generic agent-level tool extension
        self._custom_agent_tools: dict[str, Callable[[dict, Any], str]] = {}
        self._pending_toolsets_rebuild: list[str] | None = None
```

- [ ] **Step 3: Fire on_agent_ready hook at end of __init__**

In `~/hermes-agent/run_agent.py`, at the end of `__init__` — after the `self.valid_tool_names` block (line ~934) and before any method definitions — add:

```python
        # Fire on_agent_ready so plugins can inject agent-level tools
        try:
            from hermes_cli.plugins import invoke_hook as _invoke_hook
            _invoke_hook("on_agent_ready", agent=self)
        except Exception as exc:
            logger.warning("on_agent_ready hook failed: %s", exc)
```

- [ ] **Step 4: Add elif for _custom_agent_tools in _invoke_tool**

In `~/hermes-agent/run_agent.py`, in `_invoke_tool()`, immediately after the `delegate_task` elif block (after `return _delegate_task(...)` at line ~5323) and before the `else:` at line ~5324:

```python
        elif function_name in self._custom_agent_tools:
            return self._custom_agent_tools[function_name](function_args, self)
```

- [ ] **Step 5: Add toolset rebuild check in main loop**

In `~/hermes-agent/run_agent.py`, in `run_conversation()`, find the sequence inside the `if assistant_message.tool_calls:` branch:

```python
                    self._session_messages = messages
                    self._save_session_log(messages)

                    # Continue loop for next response
                    continue
```

Insert between `_save_session_log(messages)` and `continue`:

```python
                    # Gate 2: check for pending toolset rebuild
                    if self._pending_toolsets_rebuild is not None:
                        self.enabled_toolsets = self._pending_toolsets_rebuild
                        self._pending_toolsets_rebuild = None
                        self.tools = get_tool_definitions(
                            enabled_toolsets=self.enabled_toolsets,
                            disabled_toolsets=self.disabled_toolsets,
                            quiet_mode=True,
                        )
                        self.valid_tool_names = {
                            tool["function"]["name"] for tool in self.tools
                        } if self.tools else set()
                        if not self.quiet_mode:
                            self._safe_print(
                                f"🔄 Tool surface rebuilt ({len(self.tools)} tools)"
                            )
```

- [ ] **Step 6: Commit Hermes changes on a named branch**

```bash
cd ~/hermes-agent
git checkout -b vizier-gate2-patch
git add hermes_cli/plugins.py run_agent.py
git commit -m "feat: generic agent-level tool extension — on_agent_ready hook + _custom_agent_tools dispatch + _pending_toolsets_rebuild"
```

---

### Task 3: switch_toolset Hermes plugin

**Files:**
- Create: `plugins/switch_toolset.py`
- Test: `tests/plugins/test_switch_toolset.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/plugins/test_switch_toolset.py
"""Tests for switch_toolset Hermes plugin."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plugins.switch_toolset import (
    VIZIER_WORKFLOW_TOOLSETS,
    _handle_switch_toolset,
)


@pytest.fixture()
def mock_agent() -> SimpleNamespace:
    """Fake agent with enabled_toolsets and _pending_toolsets_rebuild."""
    agent = SimpleNamespace(
        enabled_toolsets=["vizier-core", "code_execution", "delegation", "vizier-content"],
        _pending_toolsets_rebuild=None,
    )
    return agent


class TestHandleSwitchToolset:
    def test_switch_to_valid_toolset(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent))
        assert result["status"] == "pending"
        assert result["switching_to"] == "vizier-visual"
        assert mock_agent._pending_toolsets_rebuild is not None
        assert "vizier-visual" in mock_agent._pending_toolsets_rebuild
        # Base toolsets preserved
        assert "vizier-core" in mock_agent._pending_toolsets_rebuild
        assert "code_execution" in mock_agent._pending_toolsets_rebuild
        assert "delegation" in mock_agent._pending_toolsets_rebuild
        # Old workflow toolset removed
        assert "vizier-content" not in mock_agent._pending_toolsets_rebuild

    def test_switch_to_unknown_toolset(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-unknown"}, mock_agent))
        assert "error" in result
        assert mock_agent._pending_toolsets_rebuild is None

    def test_switch_to_fallback_loads_all(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-fallback"}, mock_agent))
        assert result["switching_to"] == "vizier-fallback"
        assert "vizier-fallback" in mock_agent._pending_toolsets_rebuild

    def test_switch_preserves_non_vizier_toolsets(self, mock_agent: SimpleNamespace) -> None:
        mock_agent.enabled_toolsets = ["vizier-core", "hermes-cli", "vizier-document"]
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent)
        assert "hermes-cli" in mock_agent._pending_toolsets_rebuild
        assert "vizier-core" in mock_agent._pending_toolsets_rebuild

    def test_two_switches_last_wins(self, mock_agent: SimpleNamespace) -> None:
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent)
        _handle_switch_toolset({"toolset_name": "vizier-audio"}, mock_agent)
        assert "vizier-audio" in mock_agent._pending_toolsets_rebuild
        assert "vizier-visual" not in mock_agent._pending_toolsets_rebuild

    def test_switch_to_already_active_is_noop(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-content"}, mock_agent))
        assert result["status"] == "pending"
        # Still works — rebuilds with same toolset
        assert "vizier-content" in mock_agent._pending_toolsets_rebuild

    def test_switch_does_not_mutate_enabled_toolsets(self, mock_agent: SimpleNamespace) -> None:
        """Switch only sets _pending_toolsets_rebuild, never touches enabled_toolsets directly.
        This ensures other tools in the same batch aren't affected mid-turn."""
        original = list(mock_agent.enabled_toolsets)
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent)
        assert mock_agent.enabled_toolsets == original  # unchanged
        assert mock_agent._pending_toolsets_rebuild is not None  # flag set


class TestRegister:
    def test_register_calls_register_tool_and_hook(self) -> None:
        from plugins.switch_toolset import register

        ctx = MagicMock()
        register(ctx)
        ctx.register_tool.assert_called_once()
        ctx.register_hook.assert_called_once_with("on_agent_ready", ctx.register_hook.call_args[0][1])

    def test_on_agent_ready_injects_handler(self) -> None:
        from plugins.switch_toolset import register

        ctx = MagicMock()
        register(ctx)
        # Extract the on_agent_ready callback
        on_ready_fn = ctx.register_hook.call_args[0][1]
        agent = SimpleNamespace(_custom_agent_tools={})
        on_ready_fn(agent)
        assert "switch_toolset" in agent._custom_agent_tools
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/plugins/test_switch_toolset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'plugins.switch_toolset'`

- [ ] **Step 3: Implement switch_toolset plugin**

```python
# plugins/switch_toolset.py
"""Hermes plugin: registers switch_toolset as an agent-level tool.

Dual registration: schema goes to registry (model sees it), execution
is intercepted by _custom_agent_tools in _invoke_tool. The registry
handler is a fallback if on_agent_ready failed to inject the real handler.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from config.toolsets import VIZIER_WORKFLOW_TOOLSETS

logger = logging.getLogger(__name__)

SWITCH_TOOLSET_SCHEMA = {
    "type": "object",
    "properties": {
        "toolset_name": {
            "type": "string",
            "description": "Target workflow toolset to switch to",
            "enum": sorted(VIZIER_WORKFLOW_TOOLSETS),
        },
    },
    "required": ["toolset_name"],
}


def _handle_switch_toolset(args: dict[str, Any], agent: Any) -> str:
    """Set the pending rebuild — main loop applies it between turns."""
    new_ts = args.get("toolset_name", "")
    if new_ts not in VIZIER_WORKFLOW_TOOLSETS:
        return json.dumps({"error": f"Unknown toolset: {new_ts}"})

    base = [t for t in agent.enabled_toolsets if t not in VIZIER_WORKFLOW_TOOLSETS]
    agent._pending_toolsets_rebuild = base + [new_ts]

    return json.dumps({
        "status": "pending",
        "switching_to": new_ts,
        "keeping": base,
        "message": f"Switching to '{new_ts}' after this turn completes.",
    })


def _fallback_handler(args: dict[str, Any], **kwargs: Any) -> str:
    logger.warning(
        "switch_toolset: agent-level handler not injected — on_agent_ready may have failed"
    )
    return json.dumps(
        {"error": "switch_toolset not available — plugin initialization failed"}
    )


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader."""
    ctx.register_tool(
        name="switch_toolset",
        toolset="vizier-core",
        schema=SWITCH_TOOLSET_SCHEMA,
        handler=_fallback_handler,
        check_fn=lambda: True,
        description="Switch the active workflow toolset mid-session",
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["switch_toolset"] = _handle_switch_toolset
        logger.info("switch_toolset registered as agent-level tool")

    ctx.register_hook("on_agent_ready", on_agent_ready)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/plugins/test_switch_toolset.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run pyright + ruff**

Run: `pyright plugins/switch_toolset.py && ruff check plugins/switch_toolset.py`

- [ ] **Step 6: Commit**

```bash
git add config/toolsets.py plugins/switch_toolset.py tests/plugins/test_switch_toolset.py
git commit -m "feat: switch_toolset plugin — agent-level tool for mid-session toolset switching"
```

---

### Task 4: Integration test — toolset switch E2E

**Files:**
- Create: `tests/test_integration_chunk1.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration_chunk1.py
"""E2E integration test for Chunk 1: toolset switching."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from plugins.switch_toolset import _handle_switch_toolset, register


class TestToolsetSwitchE2E:
    """Simulate the full flow: register → on_agent_ready → switch → rebuild."""

    def test_full_switch_flow(self) -> None:
        """Simulate: plugin register → agent init → model calls switch → rebuild."""
        # 1. Plugin registration
        ctx = MagicMock()
        register(ctx)
        on_ready_fn = ctx.register_hook.call_args[0][1]

        # 2. Agent init — on_agent_ready fires
        agent = SimpleNamespace(
            enabled_toolsets=["vizier-core", "code_execution", "delegation", "vizier-content"],
            _custom_agent_tools={},
            _pending_toolsets_rebuild=None,
        )
        on_ready_fn(agent)
        assert "switch_toolset" in agent._custom_agent_tools

        # 3. Model calls switch_toolset
        handler = agent._custom_agent_tools["switch_toolset"]
        result = json.loads(handler({"toolset_name": "vizier-visual"}, agent))
        assert result["status"] == "pending"

        # 4. Main loop would apply the rebuild
        assert agent._pending_toolsets_rebuild == [
            "vizier-core", "code_execution", "delegation", "vizier-visual"
        ]

    def test_fallback_when_plugin_not_injected(self) -> None:
        """If on_agent_ready didn't fire, registry fallback returns error."""
        from plugins.switch_toolset import _fallback_handler

        result = json.loads(_fallback_handler({"toolset_name": "vizier-visual"}))
        assert "error" in result
        assert "plugin initialization failed" in result["error"]

    def test_switch_then_switch_back(self) -> None:
        """Model switches to visual, then back to content."""
        agent = SimpleNamespace(
            enabled_toolsets=["vizier-core", "vizier-content"],
            _pending_toolsets_rebuild=None,
        )
        # Switch to visual
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, agent)
        assert "vizier-visual" in agent._pending_toolsets_rebuild

        # Simulate main loop applying the rebuild
        agent.enabled_toolsets = agent._pending_toolsets_rebuild
        agent._pending_toolsets_rebuild = None

        # Switch back to content
        _handle_switch_toolset({"toolset_name": "vizier-content"}, agent)
        assert "vizier-content" in agent._pending_toolsets_rebuild
        assert "vizier-visual" not in agent._pending_toolsets_rebuild
```

- [ ] **Step 2: Run to verify pass**

Run: `pytest tests/test_integration_chunk1.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All Gate 1 tests (134) + Chunk 1 tests (11) = 145 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_chunk1.py
git commit -m "test: Chunk 1 integration — full switch_toolset E2E flow"
```

---

## Chunk 2: Workflow Toolsets (Manifests + Scripts + Pipeline Stubs)

### Task 5: vizier-visual — playwright_screenshot

**Files:**
- Create: `manifests/visual/playwright_screenshot.yaml`
- Create: `scripts/visual/screenshot_html.py`
- Test: `tests/scripts/test_screenshot_html.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_screenshot_html.py
"""Tests for playwright_screenshot wrapper."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestScreenshotHtml:
    def test_screenshot_html_string(self, tmp_path: Path) -> None:
        """Screenshot from HTML string produces PNG file."""
        from scripts.visual.screenshot_html import run

        output = tmp_path / "output.png"
        with patch("scripts.visual.screenshot_html._render_with_playwright") as mock_render:
            mock_render.return_value = str(output)
            # Create fake output
            output.write_bytes(b"\x89PNG fake")
            result = run(
                html_content="<h1>Hello</h1>",
                output_path=str(output),
            )
        assert result["file_path"] == str(output)
        assert output.exists()

    def test_screenshot_html_file(self, tmp_path: Path) -> None:
        """Screenshot from HTML file path."""
        from scripts.visual.screenshot_html import run

        html_file = tmp_path / "input.html"
        html_file.write_text("<h1>Test</h1>")
        output = tmp_path / "output.png"

        with patch("scripts.visual.screenshot_html._render_with_playwright") as mock_render:
            mock_render.return_value = str(output)
            output.write_bytes(b"\x89PNG fake")
            result = run(
                input_path=str(html_file),
                output_path=str(output),
            )
        assert result["file_path"] == str(output)

    def test_screenshot_requires_html_or_path(self) -> None:
        """Must provide either html_content or input_path."""
        from scripts.visual.screenshot_html import run

        with pytest.raises(ValueError, match="html_content or input_path"):
            run(output_path="/tmp/out.png")

    def test_screenshot_custom_viewport(self, tmp_path: Path) -> None:
        """Custom viewport dimensions passed to Playwright."""
        from scripts.visual.screenshot_html import run

        output = tmp_path / "output.png"
        with patch("scripts.visual.screenshot_html._render_with_playwright") as mock_render:
            mock_render.return_value = str(output)
            output.write_bytes(b"\x89PNG fake")
            run(
                html_content="<h1>Hi</h1>",
                output_path=str(output),
                viewport_width=1920,
                viewport_height=1080,
            )
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs["viewport_width"] == 1920
        assert call_kwargs["viewport_height"] == 1080
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/test_screenshot_html.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create manifest**

```yaml
# manifests/visual/playwright_screenshot.yaml
name: playwright_screenshot
description: "Render HTML to PNG screenshot via Playwright"
version: "1.0"
toolset: vizier-visual

execution:
  type: python_function
  entrypoint: "scripts.visual.screenshot_html:run"
  timeout: 30

input:
  html_content:
    type: string
    required: false
    description: "Raw HTML string to render"
  input_path:
    type: string
    required: false
    description: "Path to HTML file to render"
  output_path:
    type: string
    required: true
    description: "Path for output PNG"
  viewport_width:
    type: integer
    required: false
    description: "Viewport width in pixels (default: 1280)"
  viewport_height:
    type: integer
    required: false
    description: "Viewport height in pixels (default: 800)"

output:
  file_path:
    type: string
    description: "Path to generated PNG"

retry:
  max_attempts: 2
  on: [timeout, runtime_error]
```

- [ ] **Step 4: Implement script**

```python
# scripts/visual/screenshot_html.py
"""Playwright HTML → PNG screenshot wrapper."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _render_with_playwright(
    *,
    html_path: str,
    output_path: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> str:
    """Render HTML file to PNG via Playwright (sync API)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
        )
        page.goto(f"file://{html_path}")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path


def run(
    *,
    html_content: str | None = None,
    input_path: str | None = None,
    output_path: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> dict[str, str]:
    """Render HTML to PNG. Provide html_content (string) or input_path (file)."""
    if not html_content and not input_path:
        msg = "Must provide html_content or input_path"
        raise ValueError(msg)

    if html_content:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
        tmp.write(html_content)
        tmp.close()
        html_path = tmp.name
    else:
        html_path = str(Path(input_path).resolve())  # type: ignore[arg-type]

    result_path = _render_with_playwright(
        html_path=html_path,
        output_path=output_path,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )
    logger.info("Screenshot saved to %s", result_path)
    return {"file_path": result_path}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/scripts/test_screenshot_html.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Run pyright + ruff**

Run: `pyright scripts/visual/screenshot_html.py && ruff check scripts/visual/screenshot_html.py`

- [ ] **Step 7: Commit**

```bash
git add manifests/visual/playwright_screenshot.yaml scripts/visual/screenshot_html.py tests/scripts/test_screenshot_html.py
git commit -m "feat: playwright_screenshot tool — HTML to PNG via Playwright"
```

---

### Task 6: vizier-visual — pillow_process

**Files:**
- Create: `manifests/visual/pillow_process.yaml`
- Create: `scripts/visual/process_image.py`
- Test: `tests/scripts/test_process_image.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_process_image.py
"""Tests for pillow_process wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Create a 200x200 red image."""
    img = Image.new("RGB", (200, 200), color="red")
    path = tmp_path / "input.png"
    img.save(path)
    return path


class TestProcessImage:
    def test_resize(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        output = tmp_path / "resized.png"
        result = run(
            input_path=str(sample_image),
            output_path=str(output),
            operation="resize",
            width=100,
            height=100,
        )
        assert Path(result["file_path"]).exists()
        img = Image.open(result["file_path"])
        assert img.size == (100, 100)

    def test_crop(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        output = tmp_path / "cropped.png"
        result = run(
            input_path=str(sample_image),
            output_path=str(output),
            operation="crop",
            left=10,
            top=10,
            right=110,
            bottom=110,
        )
        img = Image.open(result["file_path"])
        assert img.size == (100, 100)

    def test_rotate(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        output = tmp_path / "rotated.png"
        result = run(
            input_path=str(sample_image),
            output_path=str(output),
            operation="rotate",
            angle=90,
        )
        img = Image.open(result["file_path"])
        assert img.size == (200, 200)

    def test_unknown_operation_raises(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(
                input_path=str(sample_image),
                output_path=str(tmp_path / "out.png"),
                operation="warp",
            )
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/test_process_image.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create manifest**

```yaml
# manifests/visual/pillow_process.yaml
name: pillow_process
description: "Image manipulation — resize, crop, rotate, watermark"
version: "1.0"
toolset: vizier-visual

execution:
  type: python_function
  entrypoint: "scripts.visual.process_image:run"
  timeout: 15

input:
  input_path:
    type: string
    required: true
    description: "Path to input image"
  output_path:
    type: string
    required: true
    description: "Path for output image"
  operation:
    type: string
    required: true
    description: "Operation: resize, crop, rotate, watermark, composite, adjust_color"
  width:
    type: integer
    required: false
  height:
    type: integer
    required: false
  angle:
    type: integer
    required: false
  left:
    type: integer
    required: false
  top:
    type: integer
    required: false
  right:
    type: integer
    required: false
  bottom:
    type: integer
    required: false
  watermark_text:
    type: string
    required: false
  overlay_path:
    type: string
    required: false

output:
  file_path:
    type: string
    description: "Path to processed image"
```

- [ ] **Step 4: Implement script**

```python
# scripts/visual/process_image.py
"""Pillow image manipulation wrapper."""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_OPERATIONS = {"resize", "crop", "rotate", "watermark", "composite"}


def run(
    *,
    input_path: str,
    output_path: str,
    operation: str,
    width: int | None = None,
    height: int | None = None,
    angle: int | None = None,
    left: int | None = None,
    top: int | None = None,
    right: int | None = None,
    bottom: int | None = None,
    watermark_text: str | None = None,
    overlay_path: str | None = None,
) -> dict[str, str]:
    """Process an image with the specified operation."""
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    img = Image.open(input_path)

    if operation == "resize":
        img = img.resize((width or img.width, height or img.height))
    elif operation == "crop":
        img = img.crop((left or 0, top or 0, right or img.width, bottom or img.height))
    elif operation == "rotate":
        img = img.rotate(angle or 0, expand=True)
    elif operation == "watermark":
        draw = ImageDraw.Draw(img)
        text = watermark_text or "DRAFT"
        draw.text((10, 10), text, fill=(255, 255, 255, 128))
    elif operation == "composite":
        if overlay_path:
            overlay = Image.open(overlay_path).resize(img.size)
            img = Image.alpha_composite(img.convert("RGBA"), overlay.convert("RGBA"))

    img.save(output_path)
    logger.info("Processed image saved to %s", output_path)
    return {"file_path": output_path}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/scripts/test_process_image.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add manifests/visual/pillow_process.yaml scripts/visual/process_image.py tests/scripts/test_process_image.py
git commit -m "feat: pillow_process tool — image resize, crop, rotate, watermark"
```

---

### Task 7: vizier-visual — fal_generate

**Files:**
- Create: `manifests/visual/fal_generate.yaml`
- Create: `scripts/visual/generate_image.py`
- Test: `tests/scripts/test_generate_image.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scripts/test_generate_image.py
"""Tests for fal_generate wrapper."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGenerateImage:
    def test_generate_returns_paths(self, tmp_path: Path) -> None:
        from scripts.visual.generate_image import run

        output = tmp_path / "generated.png"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "images": [{"url": "https://fal.ai/output/abc.png"}],
        }
        mock_download = MagicMock()
        mock_download.status_code = 200
        mock_download.content = b"\x89PNG fake image data"

        with patch("httpx.post", return_value=mock_response), \
             patch("httpx.get", return_value=mock_download):
            result = run(
                prompt="A sunset over mountains",
                output_path=str(output),
            )
        assert result["file_path"] == str(output)
        assert output.exists()

    def test_generate_missing_api_key_raises(self) -> None:
        from scripts.visual.generate_image import run

        with patch.dict("os.environ", {}, clear=True), \
             pytest.raises(RuntimeError, match="FAL_KEY"):
            run(prompt="test", output_path="/tmp/out.png")

    def test_generate_api_error_raises(self, tmp_path: Path) -> None:
        from scripts.visual.generate_image import run

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        mock_response.raise_for_status.side_effect = Exception("429 Too Many Requests")

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("os.environ", {"FAL_KEY": "test-key"}), \
             pytest.raises(Exception, match="429"):
            run(prompt="test", output_path=str(tmp_path / "out.png"))
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/test_generate_image.py -v`
Expected: FAIL

- [ ] **Step 3: Create manifest**

```yaml
# manifests/visual/fal_generate.yaml
name: fal_generate
description: "AI image generation via fal.ai API"
version: "1.0"
toolset: vizier-visual

execution:
  type: python_function
  entrypoint: "scripts.visual.generate_image:run"
  timeout: 60

input:
  prompt:
    type: string
    required: true
    description: "Image generation prompt"
  output_path:
    type: string
    required: true
    description: "Path to save generated image"
  model:
    type: string
    required: false
    description: "fal.ai model ID (default: fal-ai/flux/schnell)"
  width:
    type: integer
    required: false
    description: "Image width (default: 1024)"
  height:
    type: integer
    required: false
    description: "Image height (default: 1024)"

output:
  file_path:
    type: string
    description: "Path to generated image"
  image_url:
    type: string
    description: "fal.ai hosted URL"
```

- [ ] **Step 4: Implement script**

```python
# scripts/visual/generate_image.py
"""fal.ai image generation wrapper via httpx."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

FAL_API_URL = "https://fal.run"
DEFAULT_MODEL = "fal-ai/flux/schnell"


def run(
    *,
    prompt: str,
    output_path: str,
    model: str | None = None,
    width: int = 1024,
    height: int = 1024,
) -> dict[str, str]:
    """Generate an image via fal.ai and save locally."""
    api_key = os.environ.get("FAL_KEY")
    if not api_key:
        msg = "FAL_KEY environment variable required for image generation"
        raise RuntimeError(msg)

    effective_model = model or DEFAULT_MODEL
    url = f"{FAL_API_URL}/{effective_model}"

    response = httpx.post(
        url,
        headers={"Authorization": f"Key {api_key}"},
        json={
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    image_url = data["images"][0]["url"]
    img_response = httpx.get(image_url, timeout=30)
    img_response.raise_for_status()

    Path(output_path).write_bytes(img_response.content)
    logger.info("Generated image saved to %s", output_path)
    return {"file_path": output_path, "image_url": image_url}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/scripts/test_generate_image.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add manifests/visual/fal_generate.yaml scripts/visual/generate_image.py tests/scripts/test_generate_image.py
git commit -m "feat: fal_generate tool — AI image generation via fal.ai"
```

---

### Task 8: vizier-research — pandas_analyze + matplotlib_chart

**Files:**
- Create: `manifests/research/pandas_analyze.yaml`, `manifests/research/matplotlib_chart.yaml`
- Create: `scripts/research/analyze_data.py`, `scripts/research/render_chart.py`
- Test: `tests/scripts/test_analyze_data.py`, `tests/scripts/test_render_chart.py`

- [ ] **Step 1: Write failing tests for pandas_analyze**

```python
# tests/scripts/test_analyze_data.py
"""Tests for pandas_analyze wrapper."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    csv = tmp_path / "data.csv"
    csv.write_text("name,value,category\nA,10,X\nB,20,X\nC,30,Y\nD,40,Y\n")
    return csv


class TestAnalyzeData:
    def test_describe(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        result = run(input_path=str(sample_csv), operation="describe")
        assert "value" in result["summary"]

    def test_groupby(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        result = run(
            input_path=str(sample_csv),
            operation="groupby",
            group_column="category",
            agg_column="value",
            agg_function="sum",
        )
        data = json.loads(result["summary"])
        assert len(data) == 2

    def test_filter(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        result = run(
            input_path=str(sample_csv),
            operation="filter",
            filter_expr="value > 20",
        )
        data = json.loads(result["summary"])
        assert len(data) == 2

    def test_unknown_operation_raises(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(input_path=str(sample_csv), operation="pivot_table")
```

- [ ] **Step 2: Write failing tests for matplotlib_chart**

```python
# tests/scripts/test_render_chart.py
"""Tests for matplotlib_chart wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestRenderChart:
    def test_bar_chart(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        output = tmp_path / "chart.png"
        result = run(
            chart_type="bar",
            data={"labels": ["A", "B", "C"], "values": [10, 20, 30]},
            output_path=str(output),
            title="Test Chart",
        )
        assert Path(result["file_path"]).exists()
        assert output.stat().st_size > 0

    def test_line_chart(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        output = tmp_path / "line.png"
        result = run(
            chart_type="line",
            data={"x": [1, 2, 3], "y": [10, 20, 15]},
            output_path=str(output),
        )
        assert Path(result["file_path"]).exists()

    def test_pie_chart(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        output = tmp_path / "pie.png"
        result = run(
            chart_type="pie",
            data={"labels": ["A", "B"], "values": [60, 40]},
            output_path=str(output),
        )
        assert Path(result["file_path"]).exists()

    def test_unknown_chart_type_raises(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        with pytest.raises(ValueError, match="Unknown chart_type"):
            run(
                chart_type="3d_scatter",
                data={"x": [1], "y": [1]},
                output_path=str(tmp_path / "out.png"),
            )
```

- [ ] **Step 3: Run to verify fail**

Run: `pytest tests/scripts/test_analyze_data.py tests/scripts/test_render_chart.py -v`
Expected: FAIL

- [ ] **Step 4: Create manifests**

```yaml
# manifests/research/pandas_analyze.yaml
name: pandas_analyze
description: "Load and analyze tabular data with pandas"
version: "1.0"
toolset: vizier-research

execution:
  type: python_function
  entrypoint: "scripts.research.analyze_data:run"
  timeout: 30

input:
  input_path:
    type: string
    required: true
    description: "Path to CSV, JSON, or Excel file"
  operation:
    type: string
    required: true
    description: "Operation: describe, groupby, filter"
  group_column:
    type: string
    required: false
  agg_column:
    type: string
    required: false
  agg_function:
    type: string
    required: false
    description: "sum, mean, count, min, max"
  filter_expr:
    type: string
    required: false
    description: "Pandas query expression"
  output_path:
    type: string
    required: false
    description: "Path for CSV output (optional)"

output:
  summary:
    type: string
    description: "JSON summary of result"
```

```yaml
# manifests/research/matplotlib_chart.yaml
name: matplotlib_chart
description: "Generate charts — bar, line, pie, scatter, heatmap"
version: "1.0"
toolset: vizier-research

execution:
  type: python_function
  entrypoint: "scripts.research.render_chart:run"
  timeout: 15

input:
  chart_type:
    type: string
    required: true
    description: "Chart type: bar, line, pie, scatter, heatmap"
  data:
    type: object
    required: true
    description: "Chart data dict (labels, values, x, y depending on chart type)"
  output_path:
    type: string
    required: true
    description: "Path for output PNG"
  title:
    type: string
    required: false
  xlabel:
    type: string
    required: false
  ylabel:
    type: string
    required: false

output:
  file_path:
    type: string
    description: "Path to generated chart PNG"
```

- [ ] **Step 5: Implement scripts**

```python
# scripts/research/analyze_data.py
"""Pandas data analysis wrapper."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_OPERATIONS = {"describe", "groupby", "filter"}


def run(
    *,
    input_path: str,
    operation: str,
    group_column: str | None = None,
    agg_column: str | None = None,
    agg_function: str = "sum",
    filter_expr: str | None = None,
    output_path: str | None = None,
) -> dict[str, str]:
    """Analyze tabular data with pandas."""
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    path = Path(input_path)
    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix == ".json":
        df = pd.read_json(path)
    elif path.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)  # default to CSV

    if operation == "describe":
        result_df = df.describe(include="all")
        summary = result_df.to_json()
    elif operation == "groupby":
        grouped = df.groupby(group_column)[agg_column].agg(agg_function)  # type: ignore[index]
        summary = grouped.to_json()
    elif operation == "filter":
        filtered = df.query(filter_expr)  # type: ignore[arg-type]
        summary = filtered.to_json(orient="records")

    if output_path:
        df.to_csv(output_path, index=False)

    logger.info("Analysis complete: %s on %s", operation, input_path)
    return {"summary": summary}
```

```python
# scripts/research/render_chart.py
"""Matplotlib chart generation wrapper."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

_CHART_TYPES = {"bar", "line", "pie", "scatter"}


def run(
    *,
    chart_type: str,
    data: dict[str, Any],
    output_path: str,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
) -> dict[str, str]:
    """Generate a chart and save as PNG."""
    if chart_type not in _CHART_TYPES:
        msg = f"Unknown chart_type: {chart_type}. Valid: {sorted(_CHART_TYPES)}"
        raise ValueError(msg)

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        ax.bar(data["labels"], data["values"])
    elif chart_type == "line":
        ax.plot(data["x"], data["y"])
    elif chart_type == "pie":
        ax.pie(data["values"], labels=data["labels"], autopct="%1.1f%%")
    elif chart_type == "scatter":
        ax.scatter(data["x"], data["y"])

    if title:
        ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    logger.info("Chart saved to %s", output_path)
    return {"file_path": output_path}
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/scripts/test_analyze_data.py tests/scripts/test_render_chart.py -v`
Expected: All 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add manifests/research/ scripts/research/ tests/scripts/test_analyze_data.py tests/scripts/test_render_chart.py
git commit -m "feat: pandas_analyze + matplotlib_chart tools — data analysis and chart generation"
```

---

### Task 9: vizier-audio — ffmpeg_process + edge_tts_speak

**Files:**
- Create: `manifests/audio/ffmpeg_process.yaml`, `manifests/audio/edge_tts_speak.yaml`
- Create: `scripts/audio/process_media.py`, `scripts/audio/speak_text.py`
- Test: `tests/scripts/test_process_media.py`, `tests/scripts/test_speak_text.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_process_media.py
"""Tests for ffmpeg_process wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestProcessMedia:
    def test_convert_format(self, tmp_path: Path) -> None:
        from scripts.audio.process_media import run

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"RIFF" + b"\x00" * 40)  # fake WAV header
        output = tmp_path / "output.mp3"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = run(
                input_path=str(input_file),
                output_path=str(output),
                operation="convert",
            )
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]

    def test_trim(self, tmp_path: Path) -> None:
        from scripts.audio.process_media import run

        input_file = tmp_path / "input.mp3"
        input_file.write_bytes(b"\x00" * 100)
        output = tmp_path / "trimmed.mp3"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            run(
                input_path=str(input_file),
                output_path=str(output),
                operation="trim",
                start_time="00:00:05",
                end_time="00:00:30",
            )
        cmd = mock_run.call_args[0][0]
        assert "-ss" in cmd
        assert "00:00:05" in cmd

    def test_unknown_operation_raises(self, tmp_path: Path) -> None:
        from scripts.audio.process_media import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(
                input_path=str(tmp_path / "in.mp3"),
                output_path=str(tmp_path / "out.mp3"),
                operation="reverse",
            )
```

```python
# tests/scripts/test_speak_text.py
"""Tests for edge_tts_speak wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSpeakText:
    def test_speak_produces_audio(self, tmp_path: Path) -> None:
        from scripts.audio.speak_text import run

        output = tmp_path / "speech.mp3"
        with patch("scripts.audio.speak_text._generate_speech") as mock_gen:
            mock_gen.return_value = str(output)
            output.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)  # fake MP3
            result = run(
                text="Hello world",
                output_path=str(output),
            )
        assert result["file_path"] == str(output)

    def test_speak_custom_voice(self, tmp_path: Path) -> None:
        from scripts.audio.speak_text import run

        output = tmp_path / "speech.mp3"
        with patch("scripts.audio.speak_text._generate_speech") as mock_gen:
            mock_gen.return_value = str(output)
            output.write_bytes(b"\x00" * 100)
            run(
                text="Selamat pagi",
                output_path=str(output),
                voice="ms-MY-YasminNeural",
            )
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["voice"] == "ms-MY-YasminNeural"

    def test_speak_empty_text_raises(self) -> None:
        from scripts.audio.speak_text import run

        with pytest.raises(ValueError, match="text must not be empty"):
            run(text="", output_path="/tmp/out.mp3")
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/test_process_media.py tests/scripts/test_speak_text.py -v`
Expected: FAIL

- [ ] **Step 3: Create manifests**

```yaml
# manifests/audio/ffmpeg_process.yaml
name: ffmpeg_process
description: "Audio/video processing — convert, trim, concat, normalize, extract"
version: "1.0"
toolset: vizier-audio

execution:
  type: python_function
  entrypoint: "scripts.audio.process_media:run"
  timeout: 60

input:
  input_path:
    type: string
    required: true
    description: "Path to input audio/video file"
  output_path:
    type: string
    required: true
    description: "Path for output file"
  operation:
    type: string
    required: true
    description: "Operation: convert, trim, concat, normalize, extract_audio"
  start_time:
    type: string
    required: false
    description: "Start time for trim (HH:MM:SS)"
  end_time:
    type: string
    required: false
    description: "End time for trim (HH:MM:SS)"
  concat_paths:
    type: array
    required: false
    description: "Additional files to concatenate"

output:
  file_path:
    type: string
    description: "Path to processed file"
```

```yaml
# manifests/audio/edge_tts_speak.yaml
name: edge_tts_speak
description: "Text-to-speech via Microsoft Edge TTS (free, no API key)"
version: "1.0"
toolset: vizier-audio

execution:
  type: python_function
  entrypoint: "scripts.audio.speak_text:run"
  timeout: 30

input:
  text:
    type: string
    required: true
    description: "Text to convert to speech"
  output_path:
    type: string
    required: true
    description: "Path for output MP3"
  voice:
    type: string
    required: false
    description: "Voice name (default: en-US-AriaNeural). Malay: ms-MY-YasminNeural"

output:
  file_path:
    type: string
    description: "Path to generated audio"
```

- [ ] **Step 4: Implement scripts**

```python
# scripts/audio/process_media.py
"""ffmpeg CLI wrapper for audio/video processing."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_OPERATIONS = {"convert", "trim", "concat", "normalize", "extract_audio"}


def run(
    *,
    input_path: str,
    output_path: str,
    operation: str,
    start_time: str | None = None,
    end_time: str | None = None,
    concat_paths: list[str] | None = None,
) -> dict[str, str]:
    """Process audio/video via ffmpeg."""
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    cmd: list[str] = ["ffmpeg", "-y"]

    if operation == "convert":
        cmd += ["-i", input_path, output_path]
    elif operation == "trim":
        cmd += ["-i", input_path]
        if start_time:
            cmd += ["-ss", start_time]
        if end_time:
            cmd += ["-to", end_time]
        cmd += ["-c", "copy", output_path]
    elif operation == "normalize":
        cmd += ["-i", input_path, "-af", "loudnorm", output_path]
    elif operation == "extract_audio":
        cmd += ["-i", input_path, "-vn", "-acodec", "libmp3lame", output_path]

    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    logger.info("ffmpeg %s complete: %s", operation, output_path)
    return {"file_path": output_path}
```

```python
# scripts/audio/speak_text.py
"""Edge TTS text-to-speech wrapper."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AriaNeural"


async def _async_generate(text: str, output_path: str, voice: str) -> str:
    """Async edge-tts generation."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    return output_path


def _generate_speech(*, text: str, output_path: str, voice: str) -> str:
    """Sync wrapper around async edge-tts."""
    return asyncio.run(_async_generate(text, output_path, voice))


def run(
    *,
    text: str,
    output_path: str,
    voice: str | None = None,
) -> dict[str, str]:
    """Generate speech from text via Edge TTS."""
    if not text.strip():
        msg = "text must not be empty"
        raise ValueError(msg)

    effective_voice = voice or DEFAULT_VOICE
    result_path = _generate_speech(
        text=text,
        output_path=output_path,
        voice=effective_voice,
    )
    logger.info("TTS saved to %s (voice: %s)", result_path, effective_voice)
    return {"file_path": result_path}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/scripts/test_process_media.py tests/scripts/test_speak_text.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add manifests/audio/ scripts/audio/ tests/scripts/test_process_media.py tests/scripts/test_speak_text.py
git commit -m "feat: ffmpeg_process + edge_tts_speak tools — audio processing and TTS"
```

---

### Task 10: vizier-document expanded — pandoc_convert + pypdf_merge

**Files:**
- Create: `manifests/document/pandoc_convert.yaml`, `manifests/document/pypdf_merge.yaml`
- Create: `scripts/document/convert_format.py`, `scripts/document/merge_pdfs.py`
- Test: `tests/scripts/test_convert_format.py`, `tests/scripts/test_merge_pdfs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_convert_format.py
"""Tests for pandoc_convert wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestConvertFormat:
    def test_markdown_to_html(self, tmp_path: Path) -> None:
        from scripts.document.convert_format import run

        md_file = tmp_path / "input.md"
        md_file.write_text("# Hello\n\nWorld")
        output = tmp_path / "output.html"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = run(
                input_path=str(md_file),
                output_path=str(output),
                from_format="markdown",
                to_format="html",
            )
        cmd = mock_run.call_args[0][0]
        assert "pandoc" in cmd[0]
        assert "-f" in cmd
        assert "markdown" in cmd

    def test_auto_detect_format(self, tmp_path: Path) -> None:
        from scripts.document.convert_format import run

        md_file = tmp_path / "input.md"
        md_file.write_text("# Test")
        output = tmp_path / "output.docx"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            run(input_path=str(md_file), output_path=str(output))
        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert "markdown" in cmd  # auto-detected from .md
        assert "docx" in cmd      # auto-detected from .docx
```

```python
# tests/scripts/test_merge_pdfs.py
"""Tests for pypdf_merge wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter


@pytest.fixture()
def sample_pdfs(tmp_path: Path) -> list[Path]:
    """Create 2 minimal PDFs."""
    pdfs = []
    for i in range(2):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        path = tmp_path / f"doc{i}.pdf"
        with open(path, "wb") as f:
            writer.write(f)
        pdfs.append(path)
    return pdfs


class TestMergePdfs:
    def test_merge_two_pdfs(self, sample_pdfs: list[Path], tmp_path: Path) -> None:
        from scripts.document.merge_pdfs import run

        output = tmp_path / "merged.pdf"
        result = run(
            input_paths=[str(p) for p in sample_pdfs],
            output_path=str(output),
            operation="merge",
        )
        assert Path(result["file_path"]).exists()
        assert output.stat().st_size > 0

    def test_extract_page(self, sample_pdfs: list[Path], tmp_path: Path) -> None:
        from scripts.document.merge_pdfs import run

        output = tmp_path / "extracted.pdf"
        result = run(
            input_paths=[str(sample_pdfs[0])],
            output_path=str(output),
            operation="extract",
            pages=[0],
        )
        assert Path(result["file_path"]).exists()

    def test_unknown_operation_raises(self, sample_pdfs: list[Path], tmp_path: Path) -> None:
        from scripts.document.merge_pdfs import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(
                input_paths=[str(sample_pdfs[0])],
                output_path=str(tmp_path / "out.pdf"),
                operation="encrypt",
            )
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/test_convert_format.py tests/scripts/test_merge_pdfs.py -v`
Expected: FAIL

- [ ] **Step 3: Create manifests**

```yaml
# manifests/document/pandoc_convert.yaml
name: pandoc_convert
description: "Convert between document formats via pandoc"
version: "1.0"
toolset: vizier-document

execution:
  type: python_function
  entrypoint: "scripts.document.convert_format:run"
  timeout: 30

input:
  input_path:
    type: string
    required: true
    description: "Path to input file"
  output_path:
    type: string
    required: true
    description: "Path for output file"
  from_format:
    type: string
    required: false
    description: "Input format (auto-detected from extension if omitted)"
  to_format:
    type: string
    required: false
    description: "Output format (auto-detected from extension if omitted)"

output:
  file_path:
    type: string
    description: "Path to converted file"
```

```yaml
# manifests/document/pypdf_merge.yaml
name: pypdf_merge
description: "Merge, extract, or manipulate PDF files"
version: "1.0"
toolset: vizier-document

execution:
  type: python_function
  entrypoint: "scripts.document.merge_pdfs:run"
  timeout: 30

input:
  input_paths:
    type: array
    required: true
    description: "Paths to input PDF files"
  output_path:
    type: string
    required: true
    description: "Path for output PDF"
  operation:
    type: string
    required: true
    description: "Operation: merge, extract, rotate"
  pages:
    type: array
    required: false
    description: "Page indices for extract/rotate (0-indexed)"
  rotation:
    type: integer
    required: false
    description: "Rotation angle for rotate operation"

output:
  file_path:
    type: string
    description: "Path to output PDF"
```

- [ ] **Step 4: Implement scripts**

```python
# scripts/document/convert_format.py
"""Pandoc CLI wrapper for document format conversion."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_FORMAT_MAP = {
    ".md": "markdown",
    ".html": "html",
    ".docx": "docx",
    ".pdf": "pdf",
    ".tex": "latex",
    ".rst": "rst",
    ".txt": "plain",
}


def run(
    *,
    input_path: str,
    output_path: str,
    from_format: str | None = None,
    to_format: str | None = None,
) -> dict[str, str]:
    """Convert between document formats via pandoc."""
    in_path = Path(input_path)
    out_path = Path(output_path)

    effective_from = from_format or _FORMAT_MAP.get(in_path.suffix, "markdown")
    effective_to = to_format or _FORMAT_MAP.get(out_path.suffix, "html")

    cmd = [
        "pandoc",
        "-f", effective_from,
        "-t", effective_to,
        "-o", str(out_path),
        str(in_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    logger.info("Converted %s → %s", in_path.name, out_path.name)
    return {"file_path": str(out_path)}
```

```python
# scripts/document/merge_pdfs.py
"""pypdf PDF manipulation wrapper."""
from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_OPERATIONS = {"merge", "extract", "rotate"}


def run(
    *,
    input_paths: list[str],
    output_path: str,
    operation: str,
    pages: list[int] | None = None,
    rotation: int | None = None,
) -> dict[str, str]:
    """Merge, extract, or rotate PDF pages."""
    if operation not in _OPERATIONS:
        msg = f"Unknown operation: {operation}. Valid: {sorted(_OPERATIONS)}"
        raise ValueError(msg)

    writer = PdfWriter()

    if operation == "merge":
        for pdf_path in input_paths:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                writer.add_page(page)
    elif operation == "extract":
        reader = PdfReader(input_paths[0])
        for idx in (pages or []):
            writer.add_page(reader.pages[idx])
    elif operation == "rotate":
        reader = PdfReader(input_paths[0])
        for i, page in enumerate(reader.pages):
            if pages is None or i in pages:
                page.rotate(rotation or 90)
            writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    logger.info("PDF %s complete: %s", operation, output_path)
    return {"file_path": output_path}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/scripts/test_convert_format.py tests/scripts/test_merge_pdfs.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add manifests/document/pandoc_convert.yaml manifests/document/pypdf_merge.yaml scripts/document/convert_format.py scripts/document/merge_pdfs.py tests/scripts/test_convert_format.py tests/scripts/test_merge_pdfs.py
git commit -m "feat: pandoc_convert + pypdf_merge tools — document conversion and PDF manipulation"
```

---

### Task 11: Pipeline stubs + registry update + Chunk 2 integration test

**Files:**
- Create: `pipelines/poster_batch.py`, `pipelines/competitive_analysis.py`, `pipelines/tts_generate.py`
- Create: `pipelines/clone_converge.py` (stub — replaced in Chunk 4)
- Modify: `pipelines/_registry.yaml`
- Create: `tests/test_integration_chunk2.py`

- [ ] **Step 1: Create pipeline stubs**

Each stub follows the same pattern as Gate 1's content_generate stub:

```python
# pipelines/poster_batch.py
"""Batch poster production — CSV + template → posters via Jinja2 + Playwright.

Gate 2 stub: returns hardcoded output. Real implementation uses
vizier-visual tools (playwright_screenshot, pillow_process).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run(
    *,
    template_path: str | None = None,
    data_path: str | None = None,
    output_dir: str = "output/posters",
) -> dict[str, str | list[str]]:
    """Produce batch posters from template + data."""
    logger.info("poster_batch stub: template=%s data=%s", template_path, data_path)
    return {
        "status": "stub",
        "message": "poster_batch pipeline not yet implemented",
        "output_dir": output_dir,
        "posters": [],
    }
```

```python
# pipelines/clone_converge.py
"""Template cloning loop — vision → HTML → render → delta → iterate.

Gate 2 stub: returns hardcoded output. Chunk 4 replaces with full
convergence loop using calculate_delta + parameterize_template.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run(
    *,
    target_image_path: str,
    output_dir: str = "output/templates",
    max_iterations: int = 5,
    threshold: float = 0.80,
) -> dict[str, str | float]:
    """Clone a visual design into a reusable Jinja2 template."""
    logger.info("clone_converge stub: target=%s", target_image_path)
    return {
        "status": "stub",
        "message": "clone_converge pipeline not yet implemented",
        "target": target_image_path,
        "score": 0.0,
    }
```

```python
# pipelines/competitive_analysis.py
"""Competitive analysis — market scan → pandas analysis → chart → report.

Gate 2 stub.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run(
    *,
    topic: str,
    output_dir: str = "output/reports",
) -> dict[str, str]:
    """Run competitive analysis on a topic."""
    logger.info("competitive_analysis stub: topic=%s", topic)
    return {
        "status": "stub",
        "message": "competitive_analysis pipeline not yet implemented",
        "topic": topic,
    }
```

```python
# pipelines/tts_generate.py
"""TTS generation — text → edge-tts → ffmpeg normalize → output.

Gate 2 stub.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run(
    *,
    text: str,
    output_path: str = "output/audio/speech.mp3",
    voice: str | None = None,
) -> dict[str, str]:
    """Generate TTS audio from text."""
    logger.info("tts_generate stub: text=%s...", text[:50])
    return {
        "status": "stub",
        "message": "tts_generate pipeline not yet implemented",
        "output_path": output_path,
    }
```

- [ ] **Step 2: Update pipeline registry**

Add to `pipelines/_registry.yaml`:

```yaml
  - name: clone_converge
    description: "Clone visual design into reusable Jinja2 template via convergence loop"
    input:
      target_image_path: { type: string, required: true }
      output_dir: { type: string, required: false }
      max_iterations: { type: integer, required: false }
      threshold: { type: number, required: false }
    output:
      status: { type: string }
      score: { type: number }

  - name: poster_batch
    description: "CSV + template → batch poster production"
    input:
      template_path: { type: string, required: false }
      data_path: { type: string, required: false }
      output_dir: { type: string, required: false }
    output:
      posters: { type: array }

  - name: competitive_analysis
    description: "Market scan → data analysis → charts → report"
    input:
      topic: { type: string, required: true }
      output_dir: { type: string, required: false }
    output:
      status: { type: string }

  - name: tts_generate
    description: "Text → TTS audio via edge-tts + ffmpeg normalization"
    input:
      text: { type: string, required: true }
      output_path: { type: string, required: false }
      voice: { type: string, required: false }
    output:
      output_path: { type: string }
```

- [ ] **Step 3: Write integration test**

```python
# tests/test_integration_chunk2.py
"""E2E integration test for Chunk 2: all workflow toolsets."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from adapter.loader import load_all_manifests
from adapter.schemas import parse_manifest


class TestChunk2Integration:
    def test_all_new_manifests_parse(self) -> None:
        """Every new manifest is valid YAML with required fields."""
        manifest_dirs = [
            "manifests/visual",
            "manifests/research",
            "manifests/audio",
            "manifests/document",
        ]
        for dir_path in manifest_dirs:
            manifests_path = Path(dir_path)
            if not manifests_path.exists():
                continue
            for yaml_file in manifests_path.glob("*.yaml"):
                manifest = parse_manifest(yaml_file.read_text())
                assert manifest.name, f"Missing name in {yaml_file}"
                assert manifest.toolset, f"Missing toolset in {yaml_file}"
                assert manifest.execution, f"Missing execution in {yaml_file}"

    def test_pipeline_stubs_callable(self) -> None:
        """All pipeline stubs are importable and return stub status."""
        from pipelines.clone_converge import run as cc_run
        from pipelines.poster_batch import run as pb_run
        from pipelines.competitive_analysis import run as ca_run
        from pipelines.tts_generate import run as tts_run

        assert cc_run(target_image_path="/fake.png")["status"] == "stub"
        assert pb_run()["status"] == "stub"
        assert ca_run(topic="test")["status"] == "stub"
        assert tts_run(text="hello")["status"] == "stub"

    def test_toolset_names_match_manifests(self) -> None:
        """Manifest toolset fields match expected toolset names."""
        from config.toolsets import VIZIER_WORKFLOW_TOOLSETS

        for yaml_file in Path("manifests").rglob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            manifest = parse_manifest(yaml_file)
            assert manifest.toolset.startswith("vizier-"), (
                f"{yaml_file}: toolset '{manifest.toolset}' doesn't start with 'vizier-'"
            )
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (Gate 1 + Chunk 1 + Chunk 2)

- [ ] **Step 5: Commit**

```bash
git add pipelines/clone_converge.py pipelines/poster_batch.py pipelines/competitive_analysis.py pipelines/tts_generate.py pipelines/_registry.yaml tests/test_integration_chunk2.py
git commit -m "feat: Chunk 2 complete — 4 workflow toolsets with 9 tools, 4 pipeline stubs"
```

---

## Summary — Chunks 1-2 Complete

| Metric | Count |
|--------|-------|
| Tasks completed | 11 |
| New source files | ~30 |
| New test files | ~16 |
| Tests added | ~60 |
| Commits | ~11 |

**Chunks 3-4 continue in the next execution session.** The plan file is saved — the executing agent picks up from Task 12.

---

## Chunk 3: Parallel Sessions + Unattended Sessions + Channels

### Task 12: DeerFlow — task_decomposer

**Files:**
- Create: `augments/deerflow/task_decomposer.py`
- Test: `tests/augments/test_task_decomposer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/augments/test_task_decomposer.py
"""Tests for DeerFlow task_decomposer."""
from __future__ import annotations

import json

import pytest

from augments.deerflow.task_decomposer import decompose


class TestTaskDecomposer:
    def test_single_research_task(self) -> None:
        result = decompose("Analyze market trends for Malaysian F&B industry")
        tasks = result["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["toolsets"] == ["vizier-research"]

    def test_multi_workflow_decomposition(self) -> None:
        result = decompose(
            "Create a campaign for DMB: research the market, write social copy, design a poster"
        )
        tasks = result["tasks"]
        assert len(tasks) == 3
        toolsets_used = {t["toolsets"][0] for t in tasks}
        assert "vizier-research" in toolsets_used
        assert "vizier-content" in toolsets_used
        assert "vizier-visual" in toolsets_used

    def test_caps_at_three_tasks(self) -> None:
        result = decompose(
            "Research, write copy, design poster, create audio, build PDF report"
        )
        assert len(result["tasks"]) <= 3

    def test_fallback_to_single_task(self) -> None:
        result = decompose("Do something vague and unrecognizable")
        tasks = result["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["toolsets"] == ["vizier-fallback"]

    def test_output_format_matches_delegate_task(self) -> None:
        """Output is directly passable to delegate_task(tasks=...)."""
        result = decompose("Analyze data and generate a chart")
        for task in result["tasks"]:
            assert "goal" in task
            assert "toolsets" in task
            assert isinstance(task["toolsets"], list)

    def test_context_passed_through(self) -> None:
        result = decompose(
            "Design a poster for client DMB",
        )
        assert any("DMB" in t.get("context", "") or "DMB" in t["goal"] for t in result["tasks"])
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/augments/test_task_decomposer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# augments/deerflow/task_decomposer.py
"""Decompose complex tasks into parallel sub-task specs for delegate_task batch mode.

Output format is compatible with Hermes delegate_task(tasks=[...]).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_CHILDREN = 3

_TOOLSET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"research|analyze|data|market|trend|survey|competitor", re.IGNORECASE), "vizier-research"),
    (re.compile(r"poster|image|design|visual|screenshot|photo|graphic", re.IGNORECASE), "vizier-visual"),
    (re.compile(r"copy|content|write|social|caption|blog|article|email", re.IGNORECASE), "vizier-content"),
    (re.compile(r"pdf|report|invoice|document|convert|merge", re.IGNORECASE), "vizier-document"),
    (re.compile(r"audio|voice|tts|podcast|sound|music|speak", re.IGNORECASE), "vizier-audio"),
]


def _classify_segment(text: str) -> str:
    """Match a text segment to a toolset via keyword patterns."""
    for pattern, toolset in _TOOLSET_PATTERNS:
        if pattern.search(text):
            return toolset
    return "vizier-fallback"


def _split_into_segments(task_description: str) -> list[str]:
    """Split a compound task into segments by common delimiters."""
    segments = re.split(r",\s*(?:and\s+)?|;\s*|\band\b", task_description)
    return [s.strip() for s in segments if s.strip()]


def decompose(task_description: str) -> dict[str, Any]:
    """Decompose a task into sub-task specs for delegate_task batch mode.

    Returns:
        {"tasks": [{goal, context, toolsets}, ...], "summary": "..."}
    """
    segments = _split_into_segments(task_description)

    # Group segments by toolset to avoid duplicate toolset assignments
    toolset_groups: dict[str, list[str]] = {}
    for segment in segments:
        toolset = _classify_segment(segment)
        toolset_groups.setdefault(toolset, []).append(segment)

    tasks: list[dict[str, Any]] = []
    for toolset, segs in toolset_groups.items():
        goal = "; ".join(segs)
        tasks.append({
            "goal": goal,
            "context": task_description,
            "toolsets": [toolset],
        })

    # Cap at MAX_CHILDREN
    if len(tasks) > MAX_CHILDREN:
        logger.warning("Decomposed into %d tasks, capping at %d", len(tasks), MAX_CHILDREN)
        tasks = tasks[:MAX_CHILDREN]

    # Fallback: if no segments matched, single task with fallback
    if not tasks:
        tasks = [{
            "goal": task_description,
            "context": task_description,
            "toolsets": ["vizier-fallback"],
        }]

    summary = f"Decomposed into {len(tasks)} parallel sub-tasks"
    logger.info(summary)
    return {"tasks": tasks, "summary": summary}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/augments/test_task_decomposer.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add augments/deerflow/task_decomposer.py tests/augments/test_task_decomposer.py
git commit -m "feat: task_decomposer — decompose complex tasks for delegate_task batch mode"
```

---

### Task 13: DeerFlow — result_synthesizer

**Files:**
- Create: `augments/deerflow/result_synthesizer.py`
- Test: `tests/augments/test_result_synthesizer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/augments/test_result_synthesizer.py
"""Tests for DeerFlow result_synthesizer."""
from __future__ import annotations

import pytest

from augments.deerflow.result_synthesizer import merge


class TestResultSynthesizer:
    def test_merge_single_result(self) -> None:
        result = merge(results=["Research complete: market size is $2B"])
        assert "market size" in result["merged"]

    def test_merge_multiple_results(self) -> None:
        result = merge(results=[
            "Research: market growing 15% YoY",
            "Copy: 3 social media posts created at output/posts/",
            "Visual: poster saved to output/posters/dmb.png",
        ])
        assert "Research" in result["merged"]
        assert "Copy" in result["merged"]
        assert "Visual" in result["merged"]

    def test_dedup_file_paths(self) -> None:
        result = merge(results=[
            "Output: output/file1.pdf, output/file2.pdf",
            "Output: output/file1.pdf, output/file3.pdf",
        ])
        # file1.pdf should appear only once
        assert result["artifacts"].count("output/file1.pdf") == 1

    def test_empty_results(self) -> None:
        result = merge(results=[])
        assert result["merged"] == ""
        assert result["artifacts"] == []

    def test_report_format(self) -> None:
        result = merge(
            results=["Finding A", "Finding B"],
            output_format="report",
        )
        assert "report" in result["format"]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/augments/test_result_synthesizer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# augments/deerflow/result_synthesizer.py
"""Merge delegate_task child results into a unified deliverable.

Uses order-preserving deduplication for file paths (DeerFlow pattern).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FILE_PATH_PATTERN = re.compile(r"(?:output|tmp)/[\w/\-\.]+\.\w+")


def _extract_file_paths(text: str) -> list[str]:
    """Extract file paths from result text."""
    return _FILE_PATH_PATTERN.findall(text)


def _dedup_preserve_order(items: list[str]) -> list[str]:
    """Deduplicate while preserving order (DeerFlow dict.fromkeys pattern)."""
    return list(dict.fromkeys(items))


def merge(
    *,
    results: list[str],
    output_format: str = "summary",
) -> dict[str, Any]:
    """Merge child task results into a unified deliverable."""
    if not results:
        return {"merged": "", "artifacts": [], "format": output_format}

    # Collect all file paths, deduplicate
    all_paths: list[str] = []
    for result in results:
        all_paths.extend(_extract_file_paths(result))
    artifacts = _dedup_preserve_order(all_paths)

    # Merge text with section separators
    sections = []
    for i, result in enumerate(results, 1):
        sections.append(f"--- Result {i} ---\n{result}")
    merged = "\n\n".join(sections)

    logger.info(
        "Merged %d results, %d unique artifacts", len(results), len(artifacts)
    )
    return {
        "merged": merged,
        "artifacts": artifacts,
        "format": output_format,
        "result_count": len(results),
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/augments/test_result_synthesizer.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add augments/deerflow/result_synthesizer.py tests/augments/test_result_synthesizer.py
git commit -m "feat: result_synthesizer — merge delegate_task child outputs with dedup"
```

---

### Task 14: DeerFlow — shared_memory + orchestration plugin

**Files:**
- Create: `augments/deerflow/shared_memory.py`
- Create: `plugins/deerflow_orchestration.py`
- Test: `tests/augments/test_shared_memory.py`

- [ ] **Step 1: Write failing test**

```python
# tests/augments/test_shared_memory.py
"""Tests for DeerFlow shared_memory."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from augments.deerflow.shared_memory import SharedMemory


class TestSharedMemory:
    def test_write_and_read(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-123", base_dir=tmp_path)
        mem.write("child-1", {"observation": "Market is growing"})
        data = mem.read_all()
        assert len(data) == 1
        assert data[0]["observation"] == "Market is growing"

    def test_multiple_writes(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-456", base_dir=tmp_path)
        mem.write("child-1", {"obs": "A"})
        mem.write("child-2", {"obs": "B"})
        data = mem.read_all()
        assert len(data) == 2

    def test_cleanup(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-789", base_dir=tmp_path)
        mem.write("child-1", {"obs": "test"})
        assert mem.file_path.exists()
        mem.cleanup()
        assert not mem.file_path.exists()

    def test_read_empty(self, tmp_path: Path) -> None:
        mem = SharedMemory(session_id="test-empty", base_dir=tmp_path)
        data = mem.read_all()
        assert data == []
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/augments/test_shared_memory.py -v`
Expected: FAIL

- [ ] **Step 3: Implement shared_memory**

```python
# augments/deerflow/shared_memory.py
"""Cross-agent shared memory via debounced file-based IPC.

Thread-safe. JSON file at tmp/shared_memory_{session_id}.json.
Parent reads after children complete. Children write observations.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SharedMemory:
    """File-based shared memory for cross-agent observations."""

    def __init__(
        self,
        session_id: str,
        base_dir: Path | None = None,
    ) -> None:
        self._session_id = session_id
        self._base_dir = base_dir or Path("tmp")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def file_path(self) -> Path:
        return self._base_dir / f"shared_memory_{self._session_id}.json"

    def write(self, source_id: str, observation: dict[str, Any]) -> None:
        """Append an observation from a child agent."""
        with self._lock:
            existing = self._read_raw()
            existing.append({
                "source": source_id,
                **observation,
            })
            self.file_path.write_text(json.dumps(existing, indent=2))
        logger.debug("SharedMemory write from %s", source_id)

    def read_all(self) -> list[dict[str, Any]]:
        """Read all observations."""
        with self._lock:
            return self._read_raw()

    def cleanup(self) -> None:
        """Delete the shared memory file."""
        if self.file_path.exists():
            self.file_path.unlink()
            logger.info("SharedMemory cleaned up: %s", self.file_path)

    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            return json.loads(self.file_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
```

- [ ] **Step 4: Implement orchestration plugin**

```python
# plugins/deerflow_orchestration.py
"""Hermes plugin: registers decompose_task and merge_results as agent-level tools."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

DECOMPOSE_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "task_description": {
            "type": "string",
            "description": "The complex task to decompose into parallel sub-tasks",
        },
    },
    "required": ["task_description"],
}

MERGE_RESULTS_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Child task results from delegate_task to merge",
        },
        "output_format": {
            "type": "string",
            "enum": ["summary", "report", "campaign_package"],
            "description": "How to structure the merged output",
        },
    },
    "required": ["results"],
}


def _handle_decompose_task(args: dict[str, Any], agent: Any) -> str:
    from augments.deerflow.task_decomposer import decompose

    result = decompose(args.get("task_description", ""))
    return json.dumps(result)


def _handle_merge_results(args: dict[str, Any], agent: Any) -> str:
    from augments.deerflow.result_synthesizer import merge

    result = merge(
        results=args.get("results", []),
        output_format=args.get("output_format", "summary"),
    )
    return json.dumps(result)


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader."""
    # Register schemas (model sees these)
    ctx.register_tool(
        name="decompose_task",
        toolset="vizier-core",
        schema=DECOMPOSE_TASK_SCHEMA,
        handler=lambda args, **kw: '{"error": "Must be handled by agent loop"}',
        check_fn=lambda: True,
        description="Decompose a complex task into parallel sub-tasks for delegate_task",
    )
    ctx.register_tool(
        name="merge_results",
        toolset="vizier-core",
        schema=MERGE_RESULTS_SCHEMA,
        handler=lambda args, **kw: '{"error": "Must be handled by agent loop"}',
        check_fn=lambda: True,
        description="Merge child task results into a unified deliverable",
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["decompose_task"] = _handle_decompose_task
        agent._custom_agent_tools["merge_results"] = _handle_merge_results
        logger.info("decompose_task + merge_results registered as agent-level tools")

    ctx.register_hook("on_agent_ready", on_agent_ready)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/augments/test_shared_memory.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add augments/deerflow/shared_memory.py plugins/deerflow_orchestration.py tests/augments/test_shared_memory.py
git commit -m "feat: shared_memory + deerflow_orchestration plugin — cross-agent IPC and parallel tools"
```

---

### Task 15: Cron guard + cron loader + cron configs

**Files:**
- Create: `middleware/cron_guard.py`, `bridge/cron_loader.py`
- Create: `config/cron/content_calendar.yaml`, `config/cron/quality_review.yaml`, `config/cron/health_check.yaml`
- Test: `tests/middleware/test_cron_guard.py`, `tests/bridge/test_cron_loader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/middleware/test_cron_guard.py
"""Tests for cron_guard safety layer."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from middleware.cron_guard import check_job_safety, enforce_token_budget


class TestCronGuard:
    def test_allow_job_with_tested_tools(self) -> None:
        """Job passes when all tools have test files."""
        with patch("middleware.cron_guard._tools_have_tests") as mock:
            mock.return_value = True
            result = check_job_safety(
                toolsets=["vizier-core", "vizier-content"],
                token_budget=50000,
            )
        assert result["allowed"] is True

    def test_block_job_with_untested_tools(self) -> None:
        """Job blocked when tools lack test files."""
        with patch("middleware.cron_guard._tools_have_tests") as mock:
            mock.return_value = False
            result = check_job_safety(
                toolsets=["vizier-core", "vizier-content"],
                token_budget=50000,
            )
        assert result["allowed"] is False
        assert "untested" in result["reason"]

    def test_enforce_token_budget_within_limit(self) -> None:
        assert enforce_token_budget(used=30000, budget=50000) is True

    def test_enforce_token_budget_exceeded(self) -> None:
        assert enforce_token_budget(used=60000, budget=50000) is False

    def test_quality_threshold_hold(self) -> None:
        from middleware.cron_guard import should_hold_delivery

        assert should_hold_delivery(score=5.0, threshold=7.0) is True
        assert should_hold_delivery(score=8.0, threshold=7.0) is False
```

```python
# tests/bridge/test_cron_loader.py
"""Tests for cron_loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from bridge.cron_loader import load_cron_configs


class TestCronLoader:
    def test_load_valid_configs(self, tmp_path: Path) -> None:
        config = tmp_path / "test_job.yaml"
        config.write_text(
            "id: test_job\n"
            "schedule: '0 8 * * 1-5'\n"
            "prompt: 'Generate posts'\n"
            "toolsets:\n  - vizier-core\n  - vizier-content\n"
            "max_iterations: 30\n"
            "token_budget: 50000\n"
            "quality_threshold: 7\n"
        )
        configs = load_cron_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0]["id"] == "test_job"
        assert configs[0]["schedule"] == "0 8 * * 1-5"

    def test_skip_invalid_config(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: valid: cron: config\n")
        configs = load_cron_configs(tmp_path)
        assert len(configs) == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        configs = load_cron_configs(tmp_path)
        assert configs == []
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/middleware/test_cron_guard.py tests/bridge/test_cron_loader.py -v`
Expected: FAIL

- [ ] **Step 3: Implement cron_guard**

```python
# middleware/cron_guard.py
"""Safety layer for unattended cron sessions.

Checks tool test coverage, enforces token budget, holds delivery below threshold.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _tools_have_tests(toolsets: list[str]) -> bool:
    """Check that all tools in the given toolsets have test files.

    Uses test_parser to find test files for each script referenced by
    the toolset's manifests.
    """
    from pathlib import Path

    from adapter.schemas import parse_manifest
    from bridge.test_parser import find_test_file

    for toolset in toolsets:
        # Find manifests for this toolset
        for yaml_file in Path("manifests").rglob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            try:
                manifest = parse_manifest(yaml_file.read_text())
            except Exception:
                continue
            if manifest.toolset != toolset:
                continue
            # Check if the script has a test file
            if manifest.execution and hasattr(manifest.execution, "entrypoint"):
                module_path = manifest.execution.entrypoint.split(":")[0].replace(".", "/") + ".py"
                test_file = find_test_file(module_path)
                if test_file is None:
                    logger.warning("No test file for %s (toolset: %s)", module_path, toolset)
                    return False
    return True


def check_job_safety(
    *,
    toolsets: list[str],
    token_budget: int,
) -> dict[str, bool | str]:
    """Check if a cron job is safe to execute."""
    if not _tools_have_tests(toolsets):
        return {
            "allowed": False,
            "reason": "Job uses untested tools — blocked for safety",
        }
    return {"allowed": True, "reason": "All tools tested"}


def enforce_token_budget(*, used: int, budget: int) -> bool:
    """Return True if within budget, False if exceeded."""
    if used > budget:
        logger.warning("Token budget exceeded: %d / %d", used, budget)
        return False
    return True


def should_hold_delivery(*, score: float, threshold: float = 7.0) -> bool:
    """Return True if delivery should be held for human review."""
    return score < threshold
```

- [ ] **Step 4: Implement cron_loader**

```python
# bridge/cron_loader.py
"""Load cron YAML configs and validate them."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"id", "schedule", "prompt", "toolsets"}


def load_cron_configs(config_dir: Path) -> list[dict[str, Any]]:
    """Load and validate cron configs from a directory."""
    configs: list[dict[str, Any]] = []

    if not config_dir.exists():
        return configs

    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text())
            if not isinstance(data, dict):
                logger.warning("Invalid cron config (not a dict): %s", yaml_file)
                continue
            missing = _REQUIRED_FIELDS - set(data.keys())
            if missing:
                logger.warning("Cron config %s missing fields: %s", yaml_file, missing)
                continue
            configs.append(data)
            logger.info("Loaded cron config: %s", data["id"])
        except Exception as exc:
            logger.warning("Failed to load cron config %s: %s", yaml_file, exc)

    return configs
```

- [ ] **Step 5: Create cron config files**

```yaml
# config/cron/content_calendar.yaml
id: content_calendar
schedule: "0 8 * * 1-5"
prompt: "Generate today's scheduled social media posts for all active clients. Check config/clients/ for active clients. Use content_generate pipeline for each post."
toolsets:
  - vizier-core
  - vizier-content
max_iterations: 30
token_budget: 50000
quality_threshold: 7
```

```yaml
# config/cron/quality_review.yaml
id: quality_review
schedule: "0 9 * * 1"
prompt: "Review last week's output quality scores from prompt_logger. Flag any regressions below 7/10. Generate a summary report."
toolsets:
  - vizier-core
  - vizier-research
max_iterations: 20
token_budget: 30000
quality_threshold: 7
```

```yaml
# config/cron/health_check.yaml
id: health_check
schedule: "0 7 * * *"
prompt: "Run system health check: count token usage from prompt_logger, check error rates, verify pipeline success rates. Report anomalies."
toolsets:
  - vizier-core
max_iterations: 10
token_budget: 10000
quality_threshold: 5
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/middleware/test_cron_guard.py tests/bridge/test_cron_loader.py -v`
Expected: All 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add middleware/cron_guard.py bridge/cron_loader.py config/cron/ tests/middleware/test_cron_guard.py tests/bridge/test_cron_loader.py
git commit -m "feat: cron_guard + cron_loader — safety layer and config loading for unattended sessions"
```

---

### Task 16: Delivery channels — send_telegram + send_whatsapp

**Files:**
- Create: `manifests/delivery/send_telegram.yaml`, `manifests/delivery/send_whatsapp.yaml`
- Create: `scripts/delivery/send_telegram.py`, `scripts/delivery/send_whatsapp.py`
- Test: `tests/scripts/test_send_telegram.py`, `tests/scripts/test_send_whatsapp.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_send_telegram.py
"""Tests for send_telegram delivery wrapper."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSendTelegram:
    def test_send_text_message(self) -> None:
        from scripts.delivery.send_telegram import run

        with patch("scripts.delivery.send_telegram._send_message") as mock:
            mock.return_value = {"message_id": 123, "status": "sent"}
            result = run(
                chat_id="12345",
                text="Hello from Vizier",
            )
        assert result["status"] == "sent"
        assert result["message_id"] == 123

    def test_send_file(self, tmp_path) -> None:
        from scripts.delivery.send_telegram import run

        fake_file = tmp_path / "report.pdf"
        fake_file.write_bytes(b"%PDF-fake")

        with patch("scripts.delivery.send_telegram._send_document") as mock:
            mock.return_value = {"message_id": 456, "status": "sent"}
            result = run(
                chat_id="12345",
                file_path=str(fake_file),
            )
        assert result["status"] == "sent"

    def test_missing_chat_id_raises(self) -> None:
        from scripts.delivery.send_telegram import run

        with pytest.raises(ValueError, match="chat_id"):
            run(text="hello")
```

```python
# tests/scripts/test_send_whatsapp.py
"""Tests for send_whatsapp delivery wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSendWhatsapp:
    def test_send_text_message(self) -> None:
        from scripts.delivery.send_whatsapp import run

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("os.environ", {"WHATSAPP_TOKEN": "test", "WHATSAPP_PHONE_ID": "123"}):
            result = run(
                to_phone="+60123456789",
                text="Hello from Vizier",
            )
        assert result["status"] == "sent"

    def test_missing_env_vars_raises(self) -> None:
        from scripts.delivery.send_whatsapp import run

        with patch.dict("os.environ", {}, clear=True), \
             pytest.raises(RuntimeError, match="WHATSAPP_TOKEN"):
            run(to_phone="+60123456789", text="test")

    def test_api_error(self) -> None:
        from scripts.delivery.send_whatsapp import run

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("os.environ", {"WHATSAPP_TOKEN": "bad", "WHATSAPP_PHONE_ID": "123"}), \
             pytest.raises(Exception, match="401"):
            run(to_phone="+60123456789", text="test")
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/test_send_telegram.py tests/scripts/test_send_whatsapp.py -v`
Expected: FAIL

- [ ] **Step 3: Create manifests**

```yaml
# manifests/delivery/send_telegram.yaml
name: send_telegram
description: "Send text, files, or images via Telegram"
version: "1.0"
toolset: vizier-delivery

execution:
  type: python_function
  entrypoint: "scripts.delivery.send_telegram:run"
  timeout: 15

input:
  chat_id:
    type: string
    required: true
    description: "Telegram chat ID"
  text:
    type: string
    required: false
    description: "Text message to send"
  file_path:
    type: string
    required: false
    description: "Path to file to send"
  caption:
    type: string
    required: false
    description: "Caption for file/image"

output:
  status:
    type: string
  message_id:
    type: integer
```

```yaml
# manifests/delivery/send_whatsapp.yaml
name: send_whatsapp
description: "Send text, files, or images via WhatsApp Business API"
version: "1.0"
toolset: vizier-delivery

execution:
  type: python_function
  entrypoint: "scripts.delivery.send_whatsapp:run"
  timeout: 15

input:
  to_phone:
    type: string
    required: true
    description: "Recipient phone number (E.164 format)"
  text:
    type: string
    required: false
    description: "Text message to send"
  file_path:
    type: string
    required: false
    description: "Path to file to send"

output:
  status:
    type: string
  message_id:
    type: string
```

- [ ] **Step 4: Implement scripts**

```python
# scripts/delivery/send_telegram.py
"""Telegram delivery via python-telegram-bot."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def _async_send_message(chat_id: str, text: str, token: str) -> dict[str, Any]:
    from telegram import Bot

    bot = Bot(token=token)
    msg = await bot.send_message(chat_id=chat_id, text=text)
    return {"message_id": msg.message_id, "status": "sent"}


async def _async_send_document(
    chat_id: str, file_path: str, caption: str | None, token: str,
) -> dict[str, Any]:
    from telegram import Bot

    bot = Bot(token=token)
    with open(file_path, "rb") as f:
        msg = await bot.send_document(chat_id=chat_id, document=f, caption=caption)
    return {"message_id": msg.message_id, "status": "sent"}


def _send_message(chat_id: str, text: str, token: str) -> dict[str, Any]:
    return asyncio.run(_async_send_message(chat_id, text, token))


def _send_document(
    chat_id: str, file_path: str, caption: str | None, token: str,
) -> dict[str, Any]:
    return asyncio.run(_async_send_document(chat_id, file_path, caption, token))


def run(
    *,
    chat_id: str | None = None,
    text: str | None = None,
    file_path: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Send a message or file via Telegram."""
    if not chat_id:
        msg = "chat_id is required"
        raise ValueError(msg)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    if file_path:
        return _send_document(chat_id, file_path, caption, token)
    if text:
        return _send_message(chat_id, text, token)

    msg = "Must provide text or file_path"
    raise ValueError(msg)
```

```python
# scripts/delivery/send_whatsapp.py
"""WhatsApp Business API delivery via httpx."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v18.0"


def run(
    *,
    to_phone: str,
    text: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Send a message via WhatsApp Business API."""
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")

    if not token:
        msg = "WHATSAPP_TOKEN environment variable required"
        raise RuntimeError(msg)
    if not phone_id:
        msg = "WHATSAPP_PHONE_ID environment variable required"
        raise RuntimeError(msg)

    url = f"{WHATSAPP_API_URL}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if text:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
    else:
        msg = "text is required (file delivery not yet implemented)"
        raise ValueError(msg)

    response = httpx.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()

    message_id = data.get("messages", [{}])[0].get("id", "")
    logger.info("WhatsApp message sent: %s", message_id)
    return {"status": "sent", "message_id": message_id}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/scripts/test_send_telegram.py tests/scripts/test_send_whatsapp.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add manifests/delivery/ scripts/delivery/ tests/scripts/test_send_telegram.py tests/scripts/test_send_whatsapp.py
git commit -m "feat: send_telegram + send_whatsapp — delivery channels for Telegram and WhatsApp"
```

---

### Task 17: SOUL.md update + Chunk 3 integration test

**Files:**
- Modify: `config/SOUL.md`
- Create: `tests/test_integration_chunk3.py`

- [ ] **Step 1: Update SOUL.md with parallel orchestration instructions**

Add to `config/SOUL.md`:

```markdown
## Parallel Task Orchestration (Gate 2+)

When you receive a complex multi-workflow task:
1. Call decompose_task with the task description
   → returns {tasks: [{goal, context, toolsets}, ...]}
2. Call delegate_task with tasks=<the returned tasks array>
   → children run IN PARALLEL via ThreadPoolExecutor (max 3)
   → delegate_task returns combined results
3. Call merge_results with the child outputs
4. Deliver final output via appropriate channel

IMPORTANT: Use delegate_task(tasks=[...]) batch mode for parallelism.
Do NOT call delegate_task separately per child — that runs sequentially.

## Unattended Session Rules (Gate 2+)

- Only modules with passing tests are eligible for unattended execution
- Quality gate must pass all active layers (no override)
- Token budget cap per session — stop if exceeded
- Delivery held if quality score < 7/10 — flagged for human review
```

- [ ] **Step 2: Write integration test**

```python
# tests/test_integration_chunk3.py
"""E2E integration test for Chunk 3: parallel sessions + channels."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from augments.deerflow.task_decomposer import decompose
from augments.deerflow.result_synthesizer import merge
from augments.deerflow.shared_memory import SharedMemory


class TestChunk3Integration:
    def test_decompose_then_merge(self) -> None:
        """Full flow: decompose → (simulated delegate) → merge."""
        # Decompose
        decomposed = decompose(
            "Research the market, write social copy, design a poster for DMB"
        )
        assert len(decomposed["tasks"]) >= 2

        # Simulate delegate_task results
        child_results = [
            "Research: Malaysian F&B market growing 15% YoY. output/research/dmb_brief.md",
            "Content: 3 social posts created. output/content/dmb_post1.txt",
            "Visual: Poster saved to output/posters/dmb_campaign.png",
        ]

        # Merge
        merged = merge(results=child_results)
        assert merged["result_count"] == 3
        assert len(merged["artifacts"]) >= 3

    def test_shared_memory_across_agents(self, tmp_path: Path) -> None:
        """Children write, parent reads."""
        mem = SharedMemory(session_id="integration-test", base_dir=tmp_path)

        # Children write
        mem.write("research-child", {"finding": "Market is $2B"})
        mem.write("content-child", {"output": "3 posts created"})

        # Parent reads
        data = mem.read_all()
        assert len(data) == 2

        # Cleanup
        mem.cleanup()
        assert not mem.file_path.exists()

    def test_cron_configs_loadable(self) -> None:
        """All cron configs in config/cron/ are valid."""
        from bridge.cron_loader import load_cron_configs

        configs = load_cron_configs(Path("config/cron"))
        assert len(configs) == 3
        ids = {c["id"] for c in configs}
        assert ids == {"content_calendar", "quality_review", "health_check"}

    def test_deerflow_plugin_registers_tools(self) -> None:
        """deerflow_orchestration plugin registers both tools."""
        from plugins.deerflow_orchestration import register

        ctx = MagicMock()
        register(ctx)
        assert ctx.register_tool.call_count == 2
        tool_names = {call[1]["name"] for call in ctx.register_tool.call_args_list}
        assert tool_names == {"decompose_task", "merge_results"}
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add config/SOUL.md tests/test_integration_chunk3.py
git commit -m "feat: Chunk 3 complete — parallel sessions, cron, delivery channels"
```

---

## Chunk 4: OpenSpace + Dream-skill + Template Cloning + Quality Gates 3-6

> **Note:** Chunk 4 is the largest chunk. Tasks 18-27 cover all remaining subsystems.

### Task 18: OpenSpace — version_dag (SQLite store)

**Files:**
- Create: `augments/openspace/version_dag.py`
- Test: `tests/augments/test_version_dag.py`

- [ ] **Step 1: Write failing test**

```python
# tests/augments/test_version_dag.py
"""Tests for OpenSpace version DAG — SQLite skill lineage store."""
from __future__ import annotations

from pathlib import Path

import pytest

from augments.openspace.version_dag import SkillRecord, VersionDAG


@pytest.fixture()
def dag(tmp_path: Path) -> VersionDAG:
    return VersionDAG(db_path=tmp_path / "skills.db")


class TestVersionDAG:
    def test_save_and_retrieve(self, dag: VersionDAG) -> None:
        record = SkillRecord(
            skill_id="test__v0_abc12345",
            name="test",
            path=Path("/skills/test"),
            is_active=True,
            origin="CAPTURED",
            generation=0,
            parent_ids=[],
            change_summary="Initial capture",
        )
        dag.save(record)
        retrieved = dag.get("test__v0_abc12345")
        assert retrieved is not None
        assert retrieved.name == "test"
        assert retrieved.is_active is True

    def test_deactivate(self, dag: VersionDAG) -> None:
        record = SkillRecord(
            skill_id="fix__v0_def67890",
            name="fix",
            path=Path("/skills/fix"),
            is_active=True,
            origin="IMPORTED",
            generation=0,
            parent_ids=[],
            change_summary="Import",
        )
        dag.save(record)
        dag.deactivate("fix__v0_def67890")
        retrieved = dag.get("fix__v0_def67890")
        assert retrieved is not None
        assert retrieved.is_active is False

    def test_atomic_replace(self, dag: VersionDAG) -> None:
        """Insert new active + deactivate old in one transaction."""
        old = SkillRecord(
            skill_id="old__v0_111",
            name="old",
            path=Path("/skills/old"),
            is_active=True,
            origin="IMPORTED",
            generation=0,
            parent_ids=[],
            change_summary="Original",
        )
        dag.save(old)

        new = SkillRecord(
            skill_id="old__v1_222",
            name="old",
            path=Path("/skills/old_v1"),
            is_active=True,
            origin="FIXED",
            generation=1,
            parent_ids=["old__v0_111"],
            change_summary="Fixed bug",
        )
        dag.atomic_replace(new_record=new, old_skill_id="old__v0_111")

        assert dag.get("old__v0_111").is_active is False
        assert dag.get("old__v1_222").is_active is True

    def test_list_active(self, dag: VersionDAG) -> None:
        for i in range(3):
            dag.save(SkillRecord(
                skill_id=f"skill_{i}",
                name=f"skill_{i}",
                path=Path(f"/skills/{i}"),
                is_active=(i != 1),  # deactivate middle one
                origin="CAPTURED",
                generation=0,
                parent_ids=[],
                change_summary=f"Skill {i}",
            ))
        active = dag.list_active()
        assert len(active) == 2

    def test_get_lineage(self, dag: VersionDAG) -> None:
        dag.save(SkillRecord(
            skill_id="a__v0", name="a", path=Path("/a"),
            is_active=False, origin="IMPORTED", generation=0,
            parent_ids=[], change_summary="v0",
        ))
        dag.save(SkillRecord(
            skill_id="a__v1", name="a", path=Path("/a_v1"),
            is_active=True, origin="FIXED", generation=1,
            parent_ids=["a__v0"], change_summary="v1",
        ))
        lineage = dag.get_lineage("a__v1")
        assert len(lineage) == 2
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/augments/test_version_dag.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# augments/openspace/version_dag.py
"""SQLite store for skill lineage — version DAG with logical deactivation."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillRecord:
    """A skill record in the version DAG."""
    skill_id: str
    name: str
    path: Path
    is_active: bool
    origin: str  # IMPORTED | CAPTURED | FIXED | DERIVED
    generation: int
    parent_ids: list[str]
    change_summary: str
    total_selections: int = 0
    total_completions: int = 0


class VersionDAG:
    """SQLite-backed skill lineage store."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path("state/openspace_skills.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS skill_records (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                origin TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0,
                change_summary TEXT NOT NULL DEFAULT '',
                total_selections INTEGER NOT NULL DEFAULT 0,
                total_completions INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS skill_lineage_parents (
                skill_id TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                PRIMARY KEY (skill_id, parent_id),
                FOREIGN KEY (skill_id) REFERENCES skill_records(skill_id)
            );
        """)

    def save(self, record: SkillRecord) -> None:
        """Upsert a skill record."""
        self._conn.execute(
            """INSERT OR REPLACE INTO skill_records
               (skill_id, name, path, is_active, origin, generation, change_summary,
                total_selections, total_completions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.skill_id, record.name, str(record.path), int(record.is_active),
             record.origin, record.generation, record.change_summary,
             record.total_selections, record.total_completions),
        )
        # Save lineage
        for parent_id in record.parent_ids:
            self._conn.execute(
                "INSERT OR IGNORE INTO skill_lineage_parents (skill_id, parent_id) VALUES (?, ?)",
                (record.skill_id, parent_id),
            )
        self._conn.commit()

    def get(self, skill_id: str) -> SkillRecord | None:
        """Retrieve a skill by ID."""
        row = self._conn.execute(
            "SELECT * FROM skill_records WHERE skill_id = ?", (skill_id,)
        ).fetchone()
        if row is None:
            return None
        parent_rows = self._conn.execute(
            "SELECT parent_id FROM skill_lineage_parents WHERE skill_id = ?",
            (skill_id,),
        ).fetchall()
        return SkillRecord(
            skill_id=row[0], name=row[1], path=Path(row[2]),
            is_active=bool(row[3]), origin=row[4], generation=row[5],
            change_summary=row[6], total_selections=row[7], total_completions=row[8],
            parent_ids=[r[0] for r in parent_rows],
        )

    def deactivate(self, skill_id: str) -> None:
        """Logically deactivate a skill."""
        self._conn.execute(
            "UPDATE skill_records SET is_active = 0 WHERE skill_id = ?",
            (skill_id,),
        )
        self._conn.commit()

    def atomic_replace(self, *, new_record: SkillRecord, old_skill_id: str) -> None:
        """Insert new active record + deactivate old in one transaction."""
        with self._conn:
            self._conn.execute(
                "UPDATE skill_records SET is_active = 0 WHERE skill_id = ?",
                (old_skill_id,),
            )
            self.save(new_record)

    def list_active(self) -> list[SkillRecord]:
        """List all active skill records."""
        rows = self._conn.execute(
            "SELECT skill_id FROM skill_records WHERE is_active = 1"
        ).fetchall()
        return [self.get(r[0]) for r in rows if self.get(r[0]) is not None]

    def get_lineage(self, skill_id: str) -> list[SkillRecord]:
        """Walk the lineage DAG back to roots."""
        visited: list[SkillRecord] = []
        queue = [skill_id]
        seen: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            record = self.get(current)
            if record:
                visited.append(record)
                queue.extend(record.parent_ids)
        return visited
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/augments/test_version_dag.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add augments/openspace/version_dag.py tests/augments/test_version_dag.py
git commit -m "feat: OpenSpace version_dag — SQLite skill lineage with atomic replace"
```

---

### Task 19: OpenSpace — safety + pruner

**Files:**
- Create: `augments/openspace/safety.py`, `augments/openspace/pruner.py`
- Test: `tests/augments/test_safety.py`

- [ ] **Step 1: Write failing test**

```python
# tests/augments/test_safety.py
"""Tests for OpenSpace skill safety validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from augments.openspace.safety import check_skill_safety


class TestSkillSafety:
    def test_safe_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "good_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Good Skill\nDoes good things.")
        assert check_skill_safety(skill_dir).is_safe is True

    def test_reject_shell_injection(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Run: `rm -rf /`")
        result = check_skill_safety(skill_dir)
        assert result.is_safe is False
        assert "shell" in result.reason.lower()

    def test_reject_oversized(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "huge_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("x" * 100_000)
        result = check_skill_safety(skill_dir)
        assert result.is_safe is False
        assert "size" in result.reason.lower()

    def test_reject_missing_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "empty_skill"
        skill_dir.mkdir()
        result = check_skill_safety(skill_dir)
        assert result.is_safe is False
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/augments/test_safety.py -v`
Expected: FAIL

- [ ] **Step 3: Implement safety + pruner**

```python
# augments/openspace/safety.py
"""Skill safety validation — check before loading into Hermes."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_SKILL_SIZE = 50_000  # 50KB

_DANGEROUS_PATTERNS = [
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*(?:bash|sh)", re.IGNORECASE),
    re.compile(r"wget\s+.*&&\s*(?:chmod|bash|sh)", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),
    re.compile(r"exec\s*\(", re.IGNORECASE),
    re.compile(r"os\.system\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.call\s*\(.*shell\s*=\s*True", re.IGNORECASE),
]


@dataclass
class SafetyResult:
    is_safe: bool
    reason: str


def check_skill_safety(skill_dir: Path) -> SafetyResult:
    """Validate a skill directory before loading."""
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
```

```python
# augments/openspace/pruner.py
"""Archive stale skills that haven't been used in N sessions."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from augments.openspace.version_dag import SkillRecord, VersionDAG

logger = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD = 10  # sessions without invocation


def prune_stale_skills(
    dag: VersionDAG,
    skills_dir: Path,
    archive_dir: Path | None = None,
    threshold: int = DEFAULT_STALE_THRESHOLD,
) -> list[str]:
    """Move stale skills to archive. Returns list of pruned skill IDs."""
    archive = archive_dir or skills_dir / "_archived"
    archive.mkdir(parents=True, exist_ok=True)

    pruned: list[str] = []
    for record in dag.list_active():
        total_use = record.total_selections + record.total_completions
        if total_use == 0 and record.generation == 0:
            # Never used, not a derivative — candidate for pruning
            continue  # Skip imported skills that haven't been tested yet
        # TODO: implement session-count tracking in Gate 3

    return pruned
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/augments/test_safety.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add augments/openspace/safety.py augments/openspace/pruner.py tests/augments/test_safety.py
git commit -m "feat: OpenSpace safety + pruner — skill validation and stale skill archiving"
```

---

### Task 20: OpenSpace — capturer + generator

**Files:**
- Create: `augments/openspace/capturer.py`, `augments/openspace/generator.py`
- Create: `config/openspace.yaml`
- Test: `tests/augments/test_capturer.py`, `tests/augments/test_generator.py`

> This is the most complex task. The capturer detects repeating tool chains from structlog. The generator creates SKILL.md + pipeline drafts.

- [ ] **Step 1: Write failing tests**

```python
# tests/augments/test_capturer.py
"""Tests for OpenSpace capturer — pattern detection from structlog."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from augments.openspace.capturer import detect_repeating_chains


@pytest.fixture()
def mock_prompt_db(tmp_path: Path) -> Path:
    """Create a mock prompt_log database with repeating tool chains."""
    db_path = tmp_path / "prompt_log.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            timestamp TEXT,
            tool_name TEXT,
            tool_args TEXT,
            result TEXT
        )
    """)
    # Insert a repeating chain: fetch → render → screenshot (5+ times)
    for session in range(6):
        for step, tool in enumerate(["httpx_fetch", "jinja2_render", "playwright_screenshot"]):
            conn.execute(
                "INSERT INTO prompt_log (session_id, timestamp, tool_name, tool_args, result) VALUES (?, ?, ?, ?, ?)",
                (f"session_{session}", f"2026-04-0{session+1}", tool, "{}", "ok"),
            )
    # Insert a non-repeating chain (only 2 occurrences)
    for session in range(2):
        conn.execute(
            "INSERT INTO prompt_log (session_id, timestamp, tool_name, tool_args, result) VALUES (?, ?, ?, ?, ?)",
            (f"rare_{session}", f"2026-04-01", "pandas_analyze", "{}", "ok"),
        )
    conn.commit()
    conn.close()
    return db_path


class TestCapturer:
    def test_detect_repeating_chain(self, mock_prompt_db: Path) -> None:
        chains = detect_repeating_chains(db_path=mock_prompt_db, threshold=5)
        assert len(chains) >= 1
        # The fetch→render→screenshot chain should be detected
        chain_tools = [c["tools"] for c in chains]
        assert any(
            "httpx_fetch" in tools and "jinja2_render" in tools
            for tools in chain_tools
        )

    def test_ignore_below_threshold(self, mock_prompt_db: Path) -> None:
        chains = detect_repeating_chains(db_path=mock_prompt_db, threshold=10)
        assert len(chains) == 0

    def test_empty_database(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE prompt_log (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                timestamp TEXT,
                tool_name TEXT,
                tool_args TEXT,
                result TEXT
            )
        """)
        conn.close()
        chains = detect_repeating_chains(db_path=db_path, threshold=5)
        assert chains == []
```

```python
# tests/augments/test_generator.py
"""Tests for OpenSpace generator — SKILL.md + pipeline draft creation."""
from __future__ import annotations

from pathlib import Path

import pytest

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
            "description": "Fetch → render → screenshot",
        }
        draft_path = generate_pipeline_draft(chain=chain, output_dir=tmp_path)
        assert draft_path.exists()
        content = draft_path.read_text()
        assert "def run(" in content
        assert "httpx_fetch" in content or "fetch" in content.lower()
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/augments/test_capturer.py tests/augments/test_generator.py -v`
Expected: FAIL

- [ ] **Step 3: Create config**

```yaml
# config/openspace.yaml
# OpenSpace skill evolution configuration
capture_threshold: 5        # Minimum chain occurrences before capture
max_pipeline_drafts: 20     # Cap on _drafts/ directory
pruner_stale_sessions: 10   # Sessions without use before archiving
prompt_log_db: "state/prompt_log.db"  # Path to prompt logger SQLite
```

- [ ] **Step 4: Implement capturer**

```python
# augments/openspace/capturer.py
"""Detect repeating tool call chains from prompt_logger traces.

Scans SQLite prompt_log table, groups tool calls by session,
finds common chain patterns that repeat above threshold.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_session_chains(db_path: Path) -> dict[str, list[str]]:
    """Load tool call sequences grouped by session."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT session_id, tool_name FROM prompt_log "
        "WHERE tool_name IS NOT NULL "
        "ORDER BY session_id, timestamp, id"
    ).fetchall()
    conn.close()

    sessions: dict[str, list[str]] = {}
    for session_id, tool_name in rows:
        sessions.setdefault(session_id, []).append(tool_name)
    return sessions


def _extract_ngrams(chain: list[str], min_len: int = 2, max_len: int = 5) -> list[tuple[str, ...]]:
    """Extract all n-grams of length min_len to max_len from a tool chain."""
    ngrams: list[tuple[str, ...]] = []
    for n in range(min_len, min(max_len + 1, len(chain) + 1)):
        for i in range(len(chain) - n + 1):
            ngrams.append(tuple(chain[i:i + n]))
    return ngrams


def detect_repeating_chains(
    *,
    db_path: Path,
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Detect tool call chains that repeat across sessions.

    Returns list of {tools: [...], occurrences: int, sessions: [...]}
    """
    sessions = _load_session_chains(db_path)
    if not sessions:
        return []

    # Count n-gram occurrences across sessions
    ngram_sessions: dict[tuple[str, ...], set[str]] = {}
    for session_id, chain in sessions.items():
        seen_in_session: set[tuple[str, ...]] = set()
        for ngram in _extract_ngrams(chain):
            if ngram not in seen_in_session:
                seen_in_session.add(ngram)
                ngram_sessions.setdefault(ngram, set()).add(session_id)

    # Filter by threshold (count unique sessions, not total occurrences)
    repeating: list[dict[str, Any]] = []
    for ngram, session_ids in ngram_sessions.items():
        if len(session_ids) >= threshold:
            repeating.append({
                "tools": list(ngram),
                "occurrences": len(session_ids),
                "sessions": sorted(session_ids),
                "description": " → ".join(ngram),
            })

    # Sort by occurrences descending, deduplicate subchains
    repeating.sort(key=lambda x: (-x["occurrences"], -len(x["tools"])))

    # Remove subchains if a longer chain covers them
    filtered: list[dict[str, Any]] = []
    seen_tools: set[tuple[str, ...]] = set()
    for chain in repeating:
        tools_tuple = tuple(chain["tools"])
        is_subchain = any(
            _is_subchain(tools_tuple, existing)
            for existing in seen_tools
        )
        if not is_subchain:
            filtered.append(chain)
            seen_tools.add(tools_tuple)

    logger.info("Detected %d repeating chains (threshold=%d)", len(filtered), threshold)
    return filtered


def _is_subchain(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """Check if short is a contiguous subchain of long."""
    if len(short) >= len(long):
        return False
    s = " ".join(short)
    l = " ".join(long)
    return s in l
```

- [ ] **Step 5: Implement generator**

```python
# augments/openspace/generator.py
"""Generate SKILL.md and pipeline drafts from captured tool chains."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_skill_md(
    *,
    chain: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Generate a SKILL.md from a captured tool chain."""
    tools = chain["tools"]
    name = "_".join(tools[:3])  # First 3 tools as name
    skill_dir = output_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_content = f"""---
name: {name}
description: Collapsed pipeline for {chain['description']}
category: workflow
---

# {name}

Auto-captured from {chain['occurrences']} sessions.

## Tool Chain

{chr(10).join(f'{i+1}. `{t}`' for i, t in enumerate(tools))}

## Usage

This pattern was detected repeating across {chain['occurrences']} sessions.
Consider using `run_pipeline` with this as a collapsed pipeline.
"""
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(skill_content)
    logger.info("Generated SKILL.md: %s", skill_path)
    return skill_path


def generate_pipeline_draft(
    *,
    chain: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Generate a pipeline draft Python file from a captured chain."""
    tools = chain["tools"]
    name = "_".join(tools[:3])

    # Generate a stub pipeline that calls each tool in sequence
    tool_calls = []
    for tool in tools:
        tool_calls.append(f'    # Step: {tool}')
        tool_calls.append(f'    logger.info("Executing {tool}")')
        tool_calls.append(f'    # result = executor.run("{tool}", {{}})')

    draft_content = f'''"""Auto-generated pipeline draft: {chain["description"]}

Captured from {chain["occurrences"]} repeating sessions.
Review and customize before promoting from _drafts/.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run(**kwargs: Any) -> dict[str, Any]:
    """Execute the {name} pipeline."""
{chr(10).join(tool_calls)}
    return {{"status": "draft", "pipeline": "{name}"}}
'''
    draft_path = output_dir / f"{name}.py"
    draft_path.write_text(draft_content)
    logger.info("Generated pipeline draft: %s", draft_path)
    return draft_path
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/augments/test_capturer.py tests/augments/test_generator.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add augments/openspace/capturer.py augments/openspace/generator.py config/openspace.yaml tests/augments/test_capturer.py tests/augments/test_generator.py
git commit -m "feat: OpenSpace capturer + generator — detect repeating chains and generate pipeline drafts"
```

---

### Task 21: OpenSpace — fixer + deriver

**Files:**
- Create: `augments/openspace/fixer.py`, `augments/openspace/deriver.py`
- Test: `tests/augments/test_fixer.py`, `tests/augments/test_deriver.py`

> These modules use GPT-5.4-mini to generate patches. Tests mock the LLM calls.

- [ ] **Step 1: Write failing tests — see spec Section 6.1 for FIXED/DERIVED flow**
- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement fixer (scan errors → LLM generates patch → atomic_replace)**
- [ ] **Step 4: Implement deriver (compare scores → LLM generates enhancement → new directory)**
- [ ] **Step 5: Run tests**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat: OpenSpace fixer + deriver — auto-repair and variant promotion"
```

---

### Task 22: OpenSpace — MCP server

**Files:**
- Create: `augments/openspace/server.py`

- [ ] **Step 1: Implement FastMCP server with 4 tools**

```python
# augments/openspace/server.py
"""FastMCP server for OpenSpace skill evolution — 4 tools for Claude Code."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("openspace")


@mcp.tool()
def execute_evolution(mode: str, target_skill_id: str = "") -> str:
    """Trigger CAPTURED, FIXED, or DERIVED evolution manually."""
    # Implementation delegates to capturer/fixer/deriver
    return f"Evolution {mode} triggered for {target_skill_id or 'auto-detect'}"


@mcp.tool()
def search_skills(query: str, limit: int = 10) -> str:
    """BM25 search over active skill index."""
    return f"Searched for '{query}', limit {limit}"


@mcp.tool()
def fix_skill(skill_id: str, error_context: str) -> str:
    """Trigger FIXED evolution for a specific broken skill."""
    return f"Fix triggered for {skill_id}"


@mcp.tool()
def get_lineage(skill_id: str) -> str:
    """Return the version DAG lineage for a skill."""
    return f"Lineage for {skill_id}"
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: OpenSpace MCP server — 4 tools for Claude Code skill management"
```

---

### Task 23: Dream-skill — signals + consolidator

**Files:**
- Create: `augments/dreamskill/signals.py`, `augments/dreamskill/consolidator.py`, `augments/dreamskill/pruner.py`
- Test: `tests/augments/test_signals.py`, `tests/augments/test_consolidator.py`

> Consolidator uses Qwen 3.5 9B via Ollama. Tests mock the Ollama call.

- [ ] **Step 1: Write failing tests — see spec Section 6.2 for 4-phase model**
- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement signals (regex extraction from structlog)**
- [ ] **Step 4: Implement consolidator (4-phase: DECIDE → GATHER → CONSOLIDATE → PRUNE)**
- [ ] **Step 5: Implement pruner (MEMORY.md size management)**
- [ ] **Step 6: Run tests**
- [ ] **Step 7: Commit**

```bash
git commit -m "feat: dream-skill consolidator — 4-phase Qwen-enhanced memory consolidation"
```

---

### Task 24: Template cloning — calculate_delta

**Files:**
- Create: `scripts/visual/calculate_delta.py`
- Test: `tests/scripts/test_calculate_delta.py`

> Multi-signal image comparison. Shared with quality gate layer 3.

- [ ] **Step 1: Write failing tests — see spec Section 6.3 for 5-signal weights**
- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement (SSIM, pixelmatch, color ΔE, layout, OCR text)**
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: calculate_delta — multi-signal image comparison for template cloning + visual QA"
```

---

### Task 25: Template cloning — parameterize_template + clone_converge (full)

**Files:**
- Create: `scripts/visual/parameterize_template.py`
- Replace: `pipelines/clone_converge.py` (stub → full implementation)
- Test: `tests/scripts/test_parameterize_template.py`, `tests/pipelines/test_clone_converge_full.py`

- [ ] **Step 1: Write failing tests — see spec Section 6.3 for convergence loop**
- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement parameterize_template (Jinja2 placeholder injection)**
- [ ] **Step 4: Implement clone_converge (full convergence loop)**
- [ ] **Step 5: Run tests**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat: template cloning loop — vision → HTML → delta → converge → parameterize"
```

---

### Task 26: Quality gate layers 3-6

**Files:**
- Modify: `middleware/quality_gate.py`
- Test: `tests/middleware/test_quality_gate_extended.py`

- [ ] **Step 1: Write failing tests — see spec Section 6.4 for layers 3-6**
- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement layer 3 (visual QA — scoped to template-based renders)**
- [ ] **Step 4: Implement layer 4 (content quality — lingua-py + tone checker)**
- [ ] **Step 5: Implement layer 5 (delivery verification — httpx status)**
- [ ] **Step 6: Implement layer 6 (feedback loop — structlog)**
- [ ] **Step 7: Run tests**
- [ ] **Step 8: Commit**

```bash
git commit -m "feat: quality gate layers 3-6 — visual QA, content, delivery, feedback"
```

---

### Task 27: Chunk 4 integration test + full suite

**Files:**
- Create: `tests/test_integration_chunk4.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration_chunk4.py
"""E2E integration test for Chunk 4: augments + quality gates."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


class TestChunk4Integration:
    def test_capturer_finds_chain_and_generates_draft(self, tmp_path: Path) -> None:
        """Capturer detects a chain → generator creates draft."""
        from augments.openspace.capturer import detect_repeating_chains
        from augments.openspace.generator import generate_pipeline_draft

        # Create mock DB with repeating chain
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE prompt_log (
                id INTEGER PRIMARY KEY, session_id TEXT,
                timestamp TEXT, tool_name TEXT, tool_args TEXT, result TEXT
            )
        """)
        for s in range(6):
            for tool in ["httpx_fetch", "jinja2_render"]:
                conn.execute(
                    "INSERT INTO prompt_log VALUES (NULL, ?, ?, ?, '{}', 'ok')",
                    (f"s{s}", f"2026-04-0{s+1}", tool),
                )
        conn.commit()
        conn.close()

        chains = detect_repeating_chains(db_path=db_path, threshold=5)
        assert len(chains) >= 1

        draft_dir = tmp_path / "_drafts"
        draft_dir.mkdir()
        draft = generate_pipeline_draft(chain=chains[0], output_dir=draft_dir)
        assert draft.exists()
        assert "def run(" in draft.read_text()

    def test_version_dag_lifecycle(self, tmp_path: Path) -> None:
        """Import → fix → deactivate old → new active."""
        from augments.openspace.version_dag import SkillRecord, VersionDAG

        dag = VersionDAG(db_path=tmp_path / "test.db")
        dag.save(SkillRecord(
            skill_id="s__v0", name="s", path=Path("/s"),
            is_active=True, origin="IMPORTED", generation=0,
            parent_ids=[], change_summary="import",
        ))
        dag.atomic_replace(
            new_record=SkillRecord(
                skill_id="s__v1", name="s", path=Path("/s_v1"),
                is_active=True, origin="FIXED", generation=1,
                parent_ids=["s__v0"], change_summary="fix",
            ),
            old_skill_id="s__v0",
        )
        assert dag.get("s__v0").is_active is False
        assert dag.get("s__v1").is_active is True
        assert len(dag.get_lineage("s__v1")) == 2

    def test_quality_gate_layers_available(self) -> None:
        """Quality gate has layers 1-6 registered."""
        from middleware.quality_gate import LAYERS

        assert len(LAYERS) >= 6
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (Gate 1: 134 + Gate 2: ~180 = ~314 total)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_chunk4.py
git commit -m "test: Chunk 4 integration — OpenSpace lifecycle + quality gate 6 layers"
```

---

## Summary Table

| Chunk | Tasks | Source files | Test files | Commits |
|-------|-------|-------------|------------|---------|
| 1. Hermes patch | 1-4 | 4 | 2 | 4 |
| 2. Toolsets | 5-11 | ~22 | ~13 | 8 |
| 3. Sessions + channels | 12-17 | ~12 | ~8 | 7 |
| 4. Augments + QA | 18-27 | ~16 | ~12 | 10 |
| **Total** | **27** | **~54** | **~35** | **~29** |

**Gate 2 exit criteria (from spec Section 10) — verify each after final commit.**
