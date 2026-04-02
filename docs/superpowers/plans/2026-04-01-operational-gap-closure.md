# Gate 2 Operational Gap Closure Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between "tests pass" and "Vizier runs operationally in Hermes" — install missing deps, wire plugins to Hermes, register MCP server, connect cron loader to Hermes scheduler, replace content pipeline stub with real LLM, and set up credential env vars.

**Architecture:** No new modules. All code exists — this plan wires it together. Plugin registration goes through the existing `vizier_tools` Hermes plugin. Content pipeline gets a real Hermes `delegate_task` LLM call. Cron loader gets a `register_jobs()` function that calls Hermes scheduler API.

**Tech Stack:** Python 3.11+, Hermes Agent v0.6.0, existing vizier-pro-max modules

**Spec:** `docs/superpowers/specs/2026-04-02-gate-2-design.md`

---

## Current State

| Gap | Severity | What's Wrong |
|-----|----------|-------------|
| Missing Python deps | CRITICAL | pixelmatch, opencv-python-headless, pytesseract, lingua-py not installed (declared in pyproject.toml) |
| Gate 2 plugins not in Hermes | CRITICAL | `switch_toolset.py` and `deerflow_orchestration.py` exist in vizier-pro-max/plugins/ but aren't loaded by Hermes |
| OpenSpace MCP not configured | MEDIUM | `augments/openspace/server.py` exists but not in `.claude/settings.json` |
| Cron loader not wired | HIGH | `bridge/cron_loader.py` parses YAML but doesn't register with Hermes scheduler |
| Content pipeline stubbed | HIGH | `pipelines/content_generate.py:52` returns placeholder, not real LLM output |
| Env vars missing | MEDIUM | TELEGRAM_BOT_TOKEN, WHATSAPP_TOKEN, FAL_KEY — needed for delivery + image generation |
| Hermes on feature branch | LOW | `vizier-gate2-patch` not merged to main (but functional) |

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `~/.hermes/plugins/vizier_tools/__init__.py` | Modify | Add Gate 2 plugin loading (switch_toolset, deerflow, query_costs) |
| `~/.hermes/plugins/vizier_tools/plugin.yaml` | Modify | Declare new tools |
| `bridge/cron_loader.py` | Modify | Add `register_jobs()` that calls Hermes scheduler |
| `pipelines/content_generate.py` | Modify | Replace stub with Hermes delegate_task LLM call |
| `.claude/settings.json` (user's) | Modify | Add openspace MCP server entry |
| `config/credentials.env.example` | Create | Document required env vars |
| `tests/test_operational.py` | Create | Smoke tests for wired integration |

---

## Chunk 1: Dependencies + Plugin Wiring

### Task 1: Install missing Python deps

**Files:** None (shell only)

- [ ] **Step 1: Install missing packages**

```bash
python3 -m pip install "pixelmatch>=0.3,<1" "opencv-python-headless>=4.9,<5" "pytesseract>=0.3,<1" "lingua-py>=2.0,<3"
```

- [ ] **Step 2: Verify all imports work**

```bash
python3 -c "
import pixelmatch; print('pixelmatch OK')
import cv2; print(f'opencv {cv2.__version__} OK')
import pytesseract; print('pytesseract OK')
from lingua import LanguageDetectorBuilder; print('lingua OK')
import skimage; print(f'scikit-image {skimage.__version__} OK')
import numpy; print(f'numpy {numpy.__version__} OK')
"
```

Expected: All 6 print OK

- [ ] **Step 3: Verify calculate_delta uses real deps (not fallbacks)**

```bash
python3 -c "
from pathlib import Path
from PIL import Image
import tempfile, os
d = tempfile.mkdtemp()
img = Image.new('RGB', (100,100), (255,0,0))
a = Path(d)/'a.png'; b = Path(d)/'b.png'
img.save(str(a)); img.save(str(b))
from scripts.visual.calculate_delta import calculate_delta
r = calculate_delta(target=a, rendered=b)
print(f'SSIM={r.ssim_score:.3f} pixel_diff={r.pixel_diff_pct:.1f}% score={r.composite_score:.3f}')
assert r.composite_score > 0.95, 'Identical images should score > 0.95'
print('calculate_delta with real deps: OK')
"
```

---

### Task 2: Wire Gate 2 plugins into Hermes

**Files:**
- Modify: `~/.hermes/plugins/vizier_tools/__init__.py`
- Modify: `~/.hermes/plugins/vizier_tools/plugin.yaml`

The existing `vizier_tools/__init__.py` only registers Gate 1 tools. It needs to also load:
1. `plugins/switch_toolset.py` → switch_toolset (agent-level tool via on_agent_ready)
2. `plugins/deerflow_orchestration.py` → decompose_task, merge_results (agent-level tools)
3. `tools/query_costs.py` → query_costs (registry-level tool)

- [ ] **Step 1: Write failing test**

```python
# tests/test_operational.py
"""Smoke tests for operational wiring."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestPluginWiring:
    def test_gate2_plugins_importable(self) -> None:
        """Gate 2 plugins can be imported from vizier-pro-max."""
        from plugins.switch_toolset import register as switch_register
        from plugins.deerflow_orchestration import register as deerflow_register
        assert callable(switch_register)
        assert callable(deerflow_register)

    def test_vizier_tools_plugin_loads_gate2(self) -> None:
        """vizier_tools plugin __init__ references Gate 2 modules."""
        plugin_path = Path.home() / ".hermes" / "plugins" / "vizier_tools" / "__init__.py"
        content = plugin_path.read_text()
        assert "switch_toolset" in content
        assert "deerflow" in content or "decompose_task" in content
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest tests/test_operational.py -v`
Expected: Second test FAILS (switch_toolset not yet in plugin)

- [ ] **Step 3: Update vizier_tools plugin to load Gate 2 modules**

Add to `~/.hermes/plugins/vizier_tools/__init__.py`, inside `register()`, after the query_logs registration block:

```python
        # --- Gate 2: Agent-level tools (switch_toolset, decompose/merge) ---
        switch_mod = _import_vizier_module(
            "vizier_switch_toolset", _vizier_root / "plugins" / "switch_toolset.py"
        )
        switch_mod.register(ctx)
        logger.info("Vizier: registered switch_toolset plugin")

        deerflow_mod = _import_vizier_module(
            "vizier_deerflow", _vizier_root / "plugins" / "deerflow_orchestration.py"
        )
        deerflow_mod.register(ctx)
        logger.info("Vizier: registered deerflow orchestration plugin")

        # Gate 2: query_costs observability
        query_costs_mod = _import_vizier_module(
            "vizier_query_costs", _vizier_root / "tools" / "query_costs.py"
        )
        ctx.register_tool(
            name="query_costs",
            toolset="vizier-core",
            schema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["per_deliverable", "per_client", "model_distribution", "anomaly_history"],
                        "description": "Cost analysis mode",
                    },
                    "client_id": {"type": "string", "description": "Filter by client"},
                },
                "required": ["mode"],
            },
            handler=query_costs_mod.query_costs,
            check_fn=lambda: True,
            description="Analyze LLM cost breakdown per deliverable/client/model",
        )
        logger.info("Vizier: registered query_costs via ctx")
```

- [ ] **Step 4: Update plugin.yaml**

```yaml
name: vizier_tools
version: "0.2.0"
description: "Vizier manifest adapter — all workflow tools, switch_toolset, DeerFlow orchestration, observability"
provides_tools:
  - httpx_fetch
  - jinja2_render
  - lightrag_search
  - typst_render
  - run_pipeline
  - query_logs
  - query_costs
  - switch_toolset
  - decompose_task
  - merge_results
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_operational.py -v`
Expected: Both tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_operational.py
git commit -m "feat: wire Gate 2 plugins into Hermes — switch_toolset, deerflow, query_costs"
```

Note: `~/.hermes/plugins/` is outside the repo, so those changes aren't committed here. They're deployment configuration.

---

### Task 3: Configure OpenSpace MCP server

**Files:**
- Modify: User's `.claude/settings.json` (manual — not in repo)
- Create: `config/mcp_servers.json` (reference config, committed)

- [ ] **Step 1: Create reference config**

```json
// config/mcp_servers.json — reference config for Claude Code MCP servers
// Copy the openspace entry to ~/.claude/settings.json under mcpServers
{
  "openspace": {
    "command": "python3",
    "args": ["-m", "augments.openspace.server"],
    "cwd": "~/vizier-pro-max"
  }
}
```

- [ ] **Step 2: Verify server starts**

```bash
cd ~/vizier-pro-max && timeout 5 python3 -m augments.openspace.server 2>&1 || true
```

Expected: No import errors. Server starts (then times out since no stdio client).

- [ ] **Step 3: Commit**

```bash
git add config/mcp_servers.json
git commit -m "docs: OpenSpace MCP server reference config for Claude Code"
```

- [ ] **Step 4: Add to Claude Code settings (manual)**

User must add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "openspace": {
      "command": "python3",
      "args": ["-m", "augments.openspace.server"],
      "cwd": "/Users/Executor/vizier-pro-max"
    }
  }
}
```

---

## Chunk 2: Content Pipeline + Cron Wiring

### Task 4: Replace content pipeline stub with real LLM call

**Files:**
- Modify: `pipelines/content_generate.py`
- Test: `tests/pipelines/test_content_generate_llm.py`

The content pipeline currently returns a hardcoded string at line 52. Replace with a Hermes delegate_task call that uses GPT-5.4-mini.

Since pipelines run inside Hermes (the model calls `run_pipeline`), the pipeline can call back into the Hermes agent via `delegate_task`. But pipelines are Python functions, not agent-level tools — they don't have access to `agent`. So we use a simpler approach: call GPT-5.4-mini directly via httpx to the Hermes API endpoint, or use the free OpenRouter endpoint.

**Design decision:** Content generation uses `httpx` to call the Hermes local LLM proxy at `http://localhost:11435/v1/chat/completions` (Hermes exposes this when running). If unavailable, fall back to stub. This keeps the pipeline independent of agent context.

- [ ] **Step 1: Write failing test**

```python
# tests/pipelines/test_content_generate_llm.py
"""Tests for content_generate pipeline with real/mocked LLM."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from pipelines.content_generate import run


class TestContentGenerateLLM:
    def test_calls_llm_when_available(self) -> None:
        """Pipeline calls LLM and returns generated content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Selamat pagi! Here is your post about Hari Raya."}}]
        }
        with patch("pipelines.content_generate._call_llm", return_value="Selamat pagi! Here is your post about Hari Raya."):
            result = run(brief="Write a Hari Raya greeting post")
        assert "Selamat pagi" in result["content"]
        assert "[Generated content for:" not in result["content"]

    def test_falls_back_to_stub_on_llm_error(self) -> None:
        """Pipeline falls back to stub if LLM is unavailable."""
        with patch("pipelines.content_generate._call_llm", return_value=None):
            result = run(brief="Write a product launch post")
        assert "[Generated content for:" in result["content"]
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest tests/pipelines/test_content_generate_llm.py -v`
Expected: FAIL (no `_call_llm` function yet)

- [ ] **Step 3: Implement LLM call in content pipeline**

Replace the stub block in `pipelines/content_generate.py` (line 51-52):

```python
# OLD (line 51-52):
# Gate 1: stub content (Gate 2+ replaces with RAG -> LLM)
content = f"[Generated content for: {brief[:100]}]"

# NEW:
content = _call_llm(brief, client_id) or f"[Generated content for: {brief[:100]}]"
```

Add the `_call_llm` function before `run()`:

```python
def _call_llm(brief: str, client_id: str | None = None) -> str | None:
    """Call GPT-5.4-mini via Hermes proxy for content generation.

    Returns generated content, or None if LLM unavailable (falls back to stub).
    """
    import httpx

    prompt = f"Generate social media content based on this brief:\n\n{brief}"
    if client_id:
        prompt += f"\n\nClient: {client_id}"

    try:
        resp = httpx.post(
            "http://localhost:11435/v1/chat/completions",
            json={
                "model": "gpt-5.4-mini",
                "messages": [
                    {"role": "system", "content": "You are Vizier, a content creation assistant for Malaysian SMEs. Write engaging social media copy."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 1024,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        logger.warning("LLM returned status %d, falling back to stub", resp.status_code)
        return None
    except Exception as exc:
        logger.warning("LLM unavailable (%s), falling back to stub", exc)
        return None
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/pipelines/test_content_generate_llm.py tests/pipelines/test_content_generate.py -v`
Expected: All PASS (new + existing)

- [ ] **Step 5: pyright + ruff**
- [ ] **Step 6: Commit**

```bash
git add pipelines/content_generate.py tests/pipelines/test_content_generate_llm.py
git commit -m "feat: content pipeline real LLM — calls Hermes proxy, falls back to stub"
```

---

### Task 5: Wire cron loader to Hermes scheduler

**Files:**
- Modify: `bridge/cron_loader.py`
- Test: `tests/bridge/test_cron_loader_register.py`

Currently `load_cron_configs()` only parses YAML. Add `register_jobs()` that takes parsed configs and registers them with Hermes cron scheduler via its Python API.

- [ ] **Step 1: Write failing test**

```python
# tests/bridge/test_cron_loader_register.py
"""Tests for cron_loader registration with Hermes scheduler."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from bridge.cron_loader import load_cron_configs, register_jobs


class TestCronLoaderRegister:
    def test_register_jobs_calls_scheduler(self, tmp_path: Path) -> None:
        """register_jobs calls Hermes scheduler for each config."""
        # Create a test config
        config_dir = tmp_path / "cron"
        config_dir.mkdir()
        (config_dir / "test.yaml").write_text(
            "id: test_job\nschedule: '0 8 * * *'\nprompt: Generate content\ntoolsets:\n  - vizier-content\n"
        )
        configs = load_cron_configs(config_dir)
        assert len(configs) == 1

        mock_scheduler = MagicMock()
        registered = register_jobs(configs, scheduler=mock_scheduler)
        assert registered == 1
        mock_scheduler.add_job.assert_called_once()

    def test_register_jobs_skips_invalid(self, tmp_path: Path) -> None:
        """register_jobs skips configs that fail registration."""
        mock_scheduler = MagicMock()
        mock_scheduler.add_job.side_effect = ValueError("bad schedule")

        registered = register_jobs(
            [{"id": "bad", "schedule": "invalid", "prompt": "x", "toolsets": []}],
            scheduler=mock_scheduler,
        )
        assert registered == 0
```

- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement register_jobs**

Add to `bridge/cron_loader.py`:

```python
def register_jobs(
    configs: list[dict[str, Any]],
    scheduler: Any,
) -> int:
    """Register cron configs with Hermes scheduler.

    Args:
        configs: Validated cron config dicts from load_cron_configs.
        scheduler: Hermes scheduler instance (has add_job method).

    Returns:
        Number of successfully registered jobs.
    """
    registered = 0
    for config in configs:
        try:
            scheduler.add_job(
                job_id=config["id"],
                schedule=config["schedule"],
                prompt=config["prompt"],
                toolsets=config.get("toolsets", []),
                budget_cap=config.get("budget_cap"),
            )
            logger.info("Registered cron job: %s (%s)", config["id"], config["schedule"])
            registered += 1
        except Exception as exc:
            logger.warning("Failed to register cron job %s: %s", config["id"], exc)

    return registered
```

- [ ] **Step 4: Run tests**
- [ ] **Step 5: pyright + ruff**
- [ ] **Step 6: Commit**

```bash
git add bridge/cron_loader.py tests/bridge/test_cron_loader_register.py
git commit -m "feat: cron loader register_jobs — wires configs to Hermes scheduler"
```

---

## Chunk 3: Credentials + Smoke Test

### Task 6: Document required credentials

**Files:**
- Create: `config/credentials.env.example`

- [ ] **Step 1: Create example env file**

```bash
# config/credentials.env.example
# Required credentials for Vizier Pro-Max operational features.
# Copy to ~/.vizier.env and fill in values. Load via: source ~/.vizier.env

# --- Delivery channels ---
# Telegram: create bot via @BotFather, get token
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# WhatsApp: Meta Business API token
WHATSAPP_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=

# --- Image generation ---
# fal.ai: https://fal.ai/dashboard/keys
FAL_KEY=

# --- Optional ---
# Hermes LLM proxy (auto-started by Hermes, usually localhost:11435)
# HERMES_LLM_PROXY=http://localhost:11435/v1
```

- [ ] **Step 2: Commit**

```bash
git add config/credentials.env.example
git commit -m "docs: credential template for delivery channels + fal.ai"
```

---

### Task 7: Full operational smoke test

**Files:**
- Create: `tests/test_operational.py` (extend from Task 2)

- [ ] **Step 1: Add operational smoke tests**

Add to `tests/test_operational.py`:

```python
class TestDependencies:
    def test_all_gate2_deps_importable(self) -> None:
        """All Gate 2 Python dependencies are installed."""
        import skimage
        import cv2
        import pytesseract
        from lingua import LanguageDetectorBuilder
        import pixelmatch
        import numpy
        import httpx
        import mcp

    def test_calculate_delta_uses_real_deps(self, tmp_path: Path) -> None:
        """calculate_delta uses scikit-image SSIM, not fallback."""
        from PIL import Image
        from scripts.visual.calculate_delta import calculate_delta
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        a = tmp_path / "a.png"; b = tmp_path / "b.png"
        img.save(str(a)); img.save(str(b))
        result = calculate_delta(target=a, rendered=b)
        assert result.ssim_score > 0.99  # Real SSIM, not MSE fallback
        assert result.composite_score > 0.95


class TestContentPipeline:
    def test_content_pipeline_has_llm_function(self) -> None:
        """Content pipeline has _call_llm (not just stub)."""
        from pipelines.content_generate import _call_llm
        assert callable(_call_llm)


class TestCronIntegration:
    def test_cron_loader_has_register_jobs(self) -> None:
        """Cron loader exports register_jobs."""
        from bridge.cron_loader import register_jobs
        assert callable(register_jobs)


class TestQualityGateFull:
    def test_visual_qa_with_real_delta(self, tmp_path: Path) -> None:
        """Layer 3 visual QA works with real image comparison."""
        from PIL import Image
        from middleware.quality_gate import validate_visual_qa
        img = Image.new("RGB", (100, 100), color=(0, 128, 255))
        target = tmp_path / "target.png"; rendered = tmp_path / "rendered.png"
        img.save(str(target)); img.save(str(rendered))
        result = validate_visual_qa(target=target, rendered=rendered, threshold=0.80)
        assert result.passed is True

    def test_content_quality_with_lingua(self) -> None:
        """Layer 4 content quality works with real lingua-py."""
        from middleware.quality_gate import validate_content_quality
        result = validate_content_quality(
            content="This product is amazing for your business growth.",
            expected_languages=["en"],
        )
        assert result.passed is True
```

- [ ] **Step 2: Run full operational test suite**

```bash
python3 -m pytest tests/test_operational.py -v
```

Expected: All tests PASS

- [ ] **Step 3: Run entire test suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 315+ tests, all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_operational.py
git commit -m "test: operational smoke tests — deps, LLM wiring, real delta, lingua"
```

---

## Summary Table

| Task | What | Severity Fixed |
|------|------|---------------|
| 1 | Install missing Python deps | CRITICAL |
| 2 | Wire Gate 2 plugins into Hermes | CRITICAL |
| 3 | Configure OpenSpace MCP server | MEDIUM |
| 4 | Content pipeline real LLM | HIGH |
| 5 | Cron loader → Hermes scheduler | HIGH |
| 6 | Document credentials | MEDIUM |
| 7 | Operational smoke tests | — |

**After this plan, remaining manual steps:**
1. Set env vars (TELEGRAM_BOT_TOKEN, WHATSAPP_TOKEN, FAL_KEY) — user-specific credentials
2. Add OpenSpace MCP server to `.claude/settings.json` — user's Claude Code config
3. Restart Hermes to pick up new plugins — `hermes restart`

**Not in scope (intentional):**
- Merging `vizier-gate2-patch` to Hermes main — that's an upstream decision
- RAG retrieval in content pipeline — deferred to Gate 3 per spec
- Real end-to-end with Telegram delivery — requires credentials
