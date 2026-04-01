# Gate 4 Track 1: Deliverable Ledger Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full cost visibility per client deliverable — every LLM call and tool execution tracked with `deliverable_id`, anomaly detection with trace export, query interface for self-inspection.

**Architecture:** Context propagation via `contextvars` attaches a `deliverable_id` to every operation in a pipeline run. A cost ledger lifecycle hook captures per-call cost data into SQLite. Anomaly detection compares costs/quality against baselines and exports full traces when thresholds are breached. A model-callable tool enables Vizier to self-inspect costs.

**Tech Stack:** Python 3.11+, SQLite (shared with prompt_logger at `~/.hermes/state.db`), contextvars, Pydantic, PyYAML, logging.

**Spec:** `docs/superpowers/specs/2026-04-01-gate-4-design.md` — Section 3

---

## File Map

| File | Responsibility |
|------|---------------|
| **Create:** `middleware/deliverable_context.py` | Context propagation — `deliverable_id` + `client_id` via contextvars |
| **Create:** `middleware/cost_ledger.py` | Lifecycle hook — captures per-call cost data to SQLite |
| **Create:** `middleware/cost_config.py` | Config loader — reads `config/cost_config.yaml` |
| **Create:** `middleware/trace_exporter.py` | Anomaly detection + trace JSON export + Telegram notification stub |
| **Create:** `tools/query_costs.py` | Model-callable tool — query cost ledger data + anomaly history |
| **Create:** `plugins/context_injector.py` | Cross-session deliverable_id injection for delegate_task |
| **Create:** `migrations/001_cost_ledger.sql` | Schema migration — new tables + views + nullable column |
| **Create:** `config/cost_config.yaml` | Baseline thresholds + retention policy + model cost rates |
| **Create:** `tests/middleware/test_deliverable_context.py` | Tests for context propagation |
| **Create:** `tests/middleware/test_cost_ledger.py` | Tests for cost ledger hook |
| **Create:** `tests/middleware/test_trace_exporter.py` | Tests for anomaly detection + export |
| **Create:** `tests/tools/test_query_costs.py` | Tests for query interface |
| **Create:** `tests/migrations/test_schema_migration.py` | Tests for DB migration |
| **Create:** `tests/plugins/test_context_injector.py` | Tests for cross-session injection |
| **Modify:** `plugins/prompt_logger.py:24-36` | Add nullable `deliverable_id` column to prompt_log table |

---

## Review Fixes Applied

Issues from plan review incorporated into this version:

- **C1 (global mutable state):** `_last_rowid` and `_call_start` replaced with `ContextVar` to prevent race conditions in concurrent calls
- **C2 (tables not initialized):** `_ensure_tables()` called lazily on first `pre_llm_call` with module-level flag
- **C3 (pipeline vs step_name):** Added `pipeline_name` column to `cost_ledger` table, separate from `step_name`
- **H1 (hardcoded cost rates):** Cost calculation moved to Python via `cost_config.py` loader, not in SQL view
- **H2 (no Telegram notification):** Added `notify_anomaly()` with defensive import of `send_telegram`
- **H3 (no anomaly history):** Added `anomaly_log` table and `_anomaly_history()` query path
- **H4 (baseline never auto-triggered):** Added auto-recalculation check in `post_llm_call`
- **H5 (patch vs monkeypatch):** Standardized on `monkeypatch.setattr` to match existing patterns
- **M1 (no context_injector):** Added `plugins/context_injector.py` task
- **M2 (no retention policy):** Added `cleanup_traces()` function
- **M3 (quality_results has no writer):** Added `record_quality()` function to cost_ledger
- **M4 (silent error catch):** Catches only specific SQLite errors, logs warnings for others
- **M5 (missing __init__.py):** Added check for `tests/middleware/__init__.py`

---

## Chunk 1: Context Propagation + Schema Migration

### Task 1: Schema Migration

**Files:**
- Create: `migrations/001_cost_ledger.sql`
- Create: `tests/migrations/__init__.py`
- Create: `tests/migrations/test_schema_migration.py`
- Modify: `plugins/prompt_logger.py:24-36`

- [ ] **Step 1: Write the migration SQL**

Create `migrations/001_cost_ledger.sql`:

```sql
-- Gate 4 Track 1: Deliverable Ledger schema migration
-- Additive only — does not drop or modify existing data

-- Add deliverable_id to existing prompt_log table (nullable, backward compatible)
ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;

-- Cost ledger table — one row per LLM call with cost data
CREATE TABLE IF NOT EXISTS cost_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deliverable_id TEXT,
    client_id TEXT,
    pipeline_name TEXT,
    step_name TEXT,
    pipeline_version TEXT,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    prompt_text TEXT,
    response_text TEXT,
    latency_ms INTEGER DEFAULT 0,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cost_ledger_deliverable
    ON cost_ledger(deliverable_id);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_client
    ON cost_ledger(client_id);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_pipeline
    ON cost_ledger(pipeline_name);

-- Cost baselines table — rolling averages per pipeline
CREATE TABLE IF NOT EXISTS cost_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_name TEXT NOT NULL,
    pipeline_version TEXT,
    avg_cost REAL DEFAULT 0.0,
    stddev REAL DEFAULT 0.0,
    sample_count INTEGER DEFAULT 0,
    updated_at REAL NOT NULL,
    UNIQUE(pipeline_name, pipeline_version)
);

-- Quality results table — per-deliverable quality gate scores
CREATE TABLE IF NOT EXISTS quality_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deliverable_id TEXT NOT NULL,
    quality_score REAL,
    all_gates_passed INTEGER DEFAULT 0,
    layer_scores_json TEXT,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_results_deliverable
    ON quality_results(deliverable_id);

-- Anomaly log table — records detected anomalies
CREATE TABLE IF NOT EXISTS anomaly_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deliverable_id TEXT NOT NULL,
    client_id TEXT,
    pipeline_name TEXT,
    reasons_json TEXT NOT NULL,
    trace_path TEXT,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomaly_log_deliverable
    ON anomaly_log(deliverable_id);

-- Deliverable summary view — one row per deliverable joining cost + quality
-- NOTE: total_cost is computed in Python via cost_config.py, not in this view.
-- This view provides token totals; cost is calculated at query time.
CREATE VIEW IF NOT EXISTS deliverable_summary AS
SELECT
    cl.deliverable_id,
    cl.client_id,
    cl.pipeline_name,
    cl.pipeline_version,
    SUM(cl.input_tokens + cl.output_tokens) AS total_tokens,
    SUM(cl.input_tokens) AS total_input_tokens,
    SUM(cl.output_tokens) AS total_output_tokens,
    qr.quality_score,
    qr.all_gates_passed,
    MIN(cl.timestamp) AS timestamp
FROM cost_ledger cl
LEFT JOIN quality_results qr ON cl.deliverable_id = qr.deliverable_id
WHERE cl.deliverable_id IS NOT NULL
GROUP BY cl.deliverable_id;
```

- [ ] **Step 2: Write failing test for migration**

Create `tests/migrations/__init__.py` (empty).

Create `tests/migrations/test_schema_migration.py`:

```python
"""Tests for Gate 4 Track 1 schema migration."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_with_prompt_log(tmp_path: Path) -> Path:
    """Create a DB with the existing prompt_log table (Gate 1 schema)."""
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO prompt_log (task_id, step, model, timestamp) VALUES (?, ?, ?, ?)",
        ["task_1", 1, "gpt-5.4-mini", 1000.0],
    )
    conn.commit()
    conn.close()
    return db_path


def _apply_migration(db_path: Path) -> None:
    sql = MIGRATION_PATH.read_text()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql)
    conn.commit()
    conn.close()


class TestSchemaMigration:
    def test_migration_file_exists(self) -> None:
        assert MIGRATION_PATH.exists()

    def test_creates_cost_ledger_table(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "cost_ledger" in tables

    def test_cost_ledger_has_pipeline_name_column(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(cost_ledger)").fetchall()]
        conn.close()
        assert "pipeline_name" in columns
        assert "step_name" in columns

    def test_creates_anomaly_log_table(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "anomaly_log" in tables

    def test_adds_deliverable_id_to_prompt_log(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(prompt_log)").fetchall()]
        conn.close()
        assert "deliverable_id" in columns

    def test_existing_prompt_log_rows_preserved(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        row = conn.execute("SELECT task_id, deliverable_id FROM prompt_log WHERE task_id = ?", ["task_1"]).fetchone()
        conn.close()
        assert row[0] == "task_1"
        assert row[1] is None

    def test_deliverable_summary_view_exists(self, db_with_prompt_log: Path) -> None:
        _apply_migration(db_with_prompt_log)
        conn = sqlite3.connect(str(db_with_prompt_log))
        views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
        conn.close()
        assert "deliverable_summary" in views
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/migrations/test_schema_migration.py -v`
Expected: FAIL — migration file doesn't exist yet

- [ ] **Step 4: Create migrations directory and verify tests pass**

Run: `mkdir -p migrations && pytest tests/migrations/test_schema_migration.py -v`
Expected: PASS

- [ ] **Step 5: Update prompt_logger.py to include deliverable_id column**

In `plugins/prompt_logger.py`, add `deliverable_id TEXT` to the CREATE TABLE in `_ensure_table` (line 34, before closing paren):

```python
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
```

- [ ] **Step 6: Run existing prompt_logger tests**

Run: `pytest tests/plugins/test_prompt_logger.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add migrations/ tests/migrations/ plugins/prompt_logger.py
git commit -m "feat: schema migration for cost ledger, anomaly log, and quality results"
```

---

### Task 2: Context Propagation

**Files:**
- Create: `middleware/deliverable_context.py`
- Create: `tests/middleware/test_deliverable_context.py`

- [ ] **Step 1: Write failing tests**

Verify `tests/middleware/__init__.py` exists (create if not).

Create `tests/middleware/test_deliverable_context.py`:

```python
"""Tests for deliverable context propagation."""
from __future__ import annotations

import uuid

import pytest

from middleware.deliverable_context import (
    clear_context,
    get_client_id,
    get_deliverable_id,
    set_context,
    start_deliverable,
)


class TestStartDeliverable:
    def test_returns_uuid4_string(self) -> None:
        clear_context()
        did = start_deliverable(client_id="client_abc")
        parsed = uuid.UUID(did, version=4)
        assert str(parsed) == did

    def test_sets_deliverable_id(self) -> None:
        clear_context()
        did = start_deliverable(client_id="client_abc")
        assert get_deliverable_id() == did

    def test_sets_client_id(self) -> None:
        clear_context()
        start_deliverable(client_id="client_abc")
        assert get_client_id() == "client_abc"

    def test_client_id_defaults_to_none(self) -> None:
        clear_context()
        start_deliverable()
        assert get_client_id() is None


class TestSetContext:
    def test_restores_existing_ids(self) -> None:
        clear_context()
        set_context(deliverable_id="existing_123", client_id="client_x")
        assert get_deliverable_id() == "existing_123"
        assert get_client_id() == "client_x"


class TestClearContext:
    def test_clears_both_ids(self) -> None:
        clear_context()
        start_deliverable(client_id="client_abc")
        clear_context()
        assert get_deliverable_id() is None
        assert get_client_id() is None


class TestGettersWithNoContext:
    def test_returns_none_by_default(self) -> None:
        clear_context()
        assert get_deliverable_id() is None
        assert get_client_id() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/middleware/test_deliverable_context.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement deliverable_context.py**

Create `middleware/deliverable_context.py`:

```python
"""Deliverable Context — propagates deliverable_id + client_id via contextvars.

In-process: automatic propagation within a session.
Cross-session: deliverable_id passed explicitly in delegate_task context
field and injected via set_context() on child session startup.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_deliverable_id: ContextVar[str | None] = ContextVar("deliverable_id", default=None)
_client_id: ContextVar[str | None] = ContextVar("client_id", default=None)


def start_deliverable(client_id: str | None = None) -> str:
    """Start a new deliverable — generates UUID4, sets context.

    Args:
        client_id: Optional client identifier for cost rollup.

    Returns:
        The generated deliverable_id (UUID4 string).
    """
    did = str(uuid.uuid4())
    _deliverable_id.set(did)
    _client_id.set(client_id)
    return did


def set_context(deliverable_id: str, client_id: str | None = None) -> None:
    """Restore context from an explicit deliverable_id (cross-session).

    Args:
        deliverable_id: Existing deliverable ID to restore.
        client_id: Optional client identifier.
    """
    _deliverable_id.set(deliverable_id)
    _client_id.set(client_id)


def get_deliverable_id() -> str | None:
    """Return the current deliverable_id, or None if not set."""
    return _deliverable_id.get()


def get_client_id() -> str | None:
    """Return the current client_id, or None if not set."""
    return _client_id.get()


def clear_context() -> None:
    """Clear deliverable context — use between pipeline runs."""
    _deliverable_id.set(None)
    _client_id.set(None)
```

- [ ] **Step 4: Run tests and pyright**

Run: `pytest tests/middleware/test_deliverable_context.py -v && pyright middleware/deliverable_context.py`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git add middleware/deliverable_context.py tests/middleware/test_deliverable_context.py
git commit -m "feat: deliverable context propagation via contextvars"
```

---

### Task 3: Config Loader + Cost Config

**Files:**
- Create: `config/cost_config.yaml`
- Create: `middleware/cost_config.py`
- Create: `tests/middleware/test_cost_config.py`

- [ ] **Step 1: Create cost_config.yaml**

```yaml
# Gate 4 Track 1: Cost tracking configuration

baselines:
  bootstrap_count: 20
  recalculate_interval: 10
  anomaly_stddev: 2.0

quality:
  min_score: 7.0

traces:
  retention_days: 90
  archive_dir: "traces/archive"
  export_dir: "traces"

model_costs:
  "gpt-5.4-mini":
    input_per_1k: 0.00015
    output_per_1k: 0.0006
  "qwen3.5:9b":
    input_per_1k: 0.0
    output_per_1k: 0.0
```

- [ ] **Step 2: Write failing test for config loader**

Create `tests/middleware/test_cost_config.py`:

```python
"""Tests for cost config loader."""
from __future__ import annotations

from middleware.cost_config import load_config


class TestLoadConfig:
    def test_loads_baseline_settings(self) -> None:
        cfg = load_config()
        assert cfg["baselines"]["bootstrap_count"] == 20
        assert cfg["baselines"]["anomaly_stddev"] == 2.0

    def test_loads_model_costs(self) -> None:
        cfg = load_config()
        assert "gpt-5.4-mini" in cfg["model_costs"]
        assert cfg["model_costs"]["gpt-5.4-mini"]["input_per_1k"] == 0.00015

    def test_loads_quality_threshold(self) -> None:
        cfg = load_config()
        assert cfg["quality"]["min_score"] == 7.0

    def test_calculates_cost(self) -> None:
        from middleware.cost_config import calculate_cost
        cost = calculate_cost("gpt-5.4-mini", input_tokens=1000, output_tokens=500)
        expected = 1000 * 0.00015 / 1000 + 500 * 0.0006 / 1000
        assert abs(cost - expected) < 1e-10

    def test_local_model_zero_cost(self) -> None:
        from middleware.cost_config import calculate_cost
        cost = calculate_cost("qwen3.5:9b", input_tokens=1000, output_tokens=500)
        assert cost == 0.0

    def test_unknown_model_zero_cost(self) -> None:
        from middleware.cost_config import calculate_cost
        cost = calculate_cost("unknown-model", input_tokens=1000, output_tokens=500)
        assert cost == 0.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/middleware/test_cost_config.py -v`
Expected: FAIL

- [ ] **Step 4: Implement cost_config.py**

Create `middleware/cost_config.py`:

```python
"""Cost Config — loads cost tracking configuration from YAML."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "cost_config.yaml"
_cached_config: dict[str, Any] | None = None


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load cost config from YAML. Cached after first load.

    Args:
        path: Override config path (for testing).

    Returns:
        Config dict with baselines, quality, traces, model_costs sections.
    """
    global _cached_config  # noqa: PLW0603
    if _cached_config is not None and path is None:
        return _cached_config

    config_path = path or _CONFIG_PATH
    if not config_path.exists():
        logger.warning("Cost config not found at %s, using defaults", config_path)
        return _defaults()

    with config_path.open() as fh:
        config = yaml.safe_load(fh)

    if path is None:
        _cached_config = config
    return config


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for a model call using configured rates.

    Args:
        model: Model identifier (e.g., "gpt-5.4-mini").
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Cost in dollars.
    """
    config = load_config()
    rates = config.get("model_costs", {}).get(model, {})
    input_rate = rates.get("input_per_1k", 0.0)
    output_rate = rates.get("output_per_1k", 0.0)
    return (input_tokens * input_rate / 1000.0) + (output_tokens * output_rate / 1000.0)


def _defaults() -> dict[str, Any]:
    """Return default config when YAML is missing."""
    return {
        "baselines": {"bootstrap_count": 20, "recalculate_interval": 10, "anomaly_stddev": 2.0},
        "quality": {"min_score": 7.0},
        "traces": {"retention_days": 90, "archive_dir": "traces/archive", "export_dir": "traces"},
        "model_costs": {},
    }
```

- [ ] **Step 5: Run tests and pyright**

Run: `pytest tests/middleware/test_cost_config.py -v && pyright middleware/cost_config.py`
Expected: PASS, 0 errors

- [ ] **Step 6: Commit**

```bash
git add config/cost_config.yaml middleware/cost_config.py tests/middleware/test_cost_config.py
git commit -m "feat: cost config loader with model cost rates"
```

---

### Task 4: Cross-Session Context Injector

**Files:**
- Create: `plugins/context_injector.py`
- Create: `tests/plugins/test_context_injector.py`

- [ ] **Step 1: Write failing test**

Create `tests/plugins/test_context_injector.py`:

```python
"""Tests for cross-session context injector plugin."""
from __future__ import annotations

import pytest

from middleware.deliverable_context import clear_context, get_client_id, get_deliverable_id
from plugins.context_injector import inject_from_task_context


class TestInjectFromTaskContext:
    def test_injects_deliverable_id(self) -> None:
        clear_context()
        inject_from_task_context({"deliverable_id": "d-123", "client_id": "acme"})
        assert get_deliverable_id() == "d-123"
        assert get_client_id() == "acme"

    def test_handles_missing_deliverable_id(self) -> None:
        clear_context()
        inject_from_task_context({"some_other_key": "value"})
        assert get_deliverable_id() is None

    def test_handles_empty_context(self) -> None:
        clear_context()
        inject_from_task_context({})
        assert get_deliverable_id() is None

    def test_handles_none_context(self) -> None:
        clear_context()
        inject_from_task_context(None)
        assert get_deliverable_id() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/plugins/test_context_injector.py -v`
Expected: FAIL

- [ ] **Step 3: Implement context_injector.py**

Create `plugins/context_injector.py`:

```python
"""Context Injector — cross-session deliverable_id propagation.

Reads deliverable_id from delegate_task context field on child
session startup and sets it in local contextvars.
"""
from __future__ import annotations

import logging
from typing import Any

from middleware.deliverable_context import set_context

logger = logging.getLogger(__name__)


def inject_from_task_context(context: dict[str, Any] | None) -> None:
    """Extract deliverable_id from task context and set in local contextvars.

    Called by Hermes on child session startup when processing a
    delegate_task batch entry with context: {deliverable_id, client_id}.

    Args:
        context: The context dict from a delegate_task batch entry.
                 May be None or missing deliverable_id.
    """
    if not context or "deliverable_id" not in context:
        return

    deliverable_id = context["deliverable_id"]
    client_id = context.get("client_id")
    set_context(deliverable_id=deliverable_id, client_id=client_id)
    logger.info(
        "Injected deliverable context: deliverable_id=%s, client_id=%s",
        deliverable_id,
        client_id,
    )
```

- [ ] **Step 4: Run tests and pyright**

Run: `pytest tests/plugins/test_context_injector.py -v && pyright plugins/context_injector.py`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git add plugins/context_injector.py tests/plugins/test_context_injector.py
git commit -m "feat: cross-session context injector for delegate_task"
```

---

## Chunk 2: Cost Ledger Lifecycle Hook

### Task 5: Cost Ledger

**Files:**
- Create: `middleware/cost_ledger.py`
- Create: `tests/middleware/test_cost_ledger.py`

- [ ] **Step 1: Write failing tests**

Create `tests/middleware/test_cost_ledger.py`:

```python
"""Tests for cost ledger lifecycle hook."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from middleware.deliverable_context import clear_context, start_deliverable

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    conn = sqlite3.connect(str(path))
    # Create prompt_log with deliverable_id (fresh install schema)
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
        )
    """)
    # Apply migration (skip ALTER since column already exists)
    sql = MIGRATION_PATH.read_text().replace(
        "ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;", ""
    )
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _patch_db(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("middleware.cost_ledger.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.cost_ledger._tables_initialized", False)
    clear_context()
    yield
    clear_context()


class TestPreLLMCallHook:
    def test_inserts_cost_ledger_row(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call

        did = start_deliverable(client_id="client_1")
        pre_llm_call(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5.4-mini",
            step_name="copy_draft",
            pipeline_name="content_generate",
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_ledger WHERE deliverable_id = ?", [did]).fetchone()
        conn.close()
        assert row is not None
        assert row["model"] == "gpt-5.4-mini"
        assert row["client_id"] == "client_1"
        assert row["step_name"] == "copy_draft"
        assert row["pipeline_name"] == "content_generate"

    def test_works_without_deliverable_context(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call

        clear_context()
        pre_llm_call(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-5.4-mini",
        )
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT deliverable_id FROM cost_ledger").fetchone()
        conn.close()
        assert row[0] is None


class TestPostLLMCallHook:
    def test_updates_token_counts_and_latency(self, db_path: Path) -> None:
        from middleware.cost_ledger import post_llm_call, pre_llm_call

        did = start_deliverable()
        pre_llm_call(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-5.4-mini",
        )
        post_llm_call(
            response_text="hello back",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_ledger WHERE deliverable_id = ?", [did]).fetchone()
        conn.close()
        assert row["input_tokens"] == 10
        assert row["output_tokens"] == 20
        assert row["response_text"] == "hello back"
        assert row["latency_ms"] >= 0


class TestRecordQuality:
    def test_inserts_quality_result(self, db_path: Path) -> None:
        from middleware.cost_ledger import record_quality

        record_quality("d-123", quality_score=8.5, all_gates_passed=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM quality_results WHERE deliverable_id = ?", ["d-123"]).fetchone()
        conn.close()
        assert row["quality_score"] == 8.5
        assert row["all_gates_passed"] == 1


class TestUpdateBaseline:
    def test_creates_baseline_after_bootstrap(self, db_path: Path) -> None:
        from middleware.cost_ledger import pre_llm_call, post_llm_call, update_baseline

        for i in range(20):
            did = start_deliverable()
            pre_llm_call(
                messages=[{"role": "user", "content": f"msg {i}"}],
                model="gpt-5.4-mini",
                step_name="draft",
                pipeline_name="content_generate",
                pipeline_version="1.0",
            )
            post_llm_call(
                response_text=f"resp {i}",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )
            clear_context()

        update_baseline("content_generate", "1.0", bootstrap_count=20)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cost_baselines WHERE pipeline_name = ?", ["content_generate"]).fetchone()
        conn.close()
        assert row is not None
        assert row["sample_count"] == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/middleware/test_cost_ledger.py -v`
Expected: FAIL

- [ ] **Step 3: Implement cost_ledger.py**

Create `middleware/cost_ledger.py`:

```python
"""Cost Ledger — Hermes lifecycle hook capturing per-call cost data.

Uses ContextVar for per-call correlation (thread/async safe).
Reads deliverable_id from deliverable_context.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from middleware.deliverable_context import get_client_id, get_deliverable_id

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")

# Per-call correlation via ContextVar (safe for concurrent/async calls)
_call_rowid: ContextVar[int | None] = ContextVar("cost_ledger_rowid", default=None)
_call_start: ContextVar[float] = ContextVar("cost_ledger_start", default=0.0)

# Lazy initialization flag
_tables_initialized = False


def _ensure_tables() -> None:
    """Lazily create cost_ledger tables if needed."""
    global _tables_initialized  # noqa: PLW0603
    if _tables_initialized:
        return

    migration = Path(__file__).parent.parent / "migrations" / "001_cost_ledger.sql"
    if not migration.exists():
        logger.warning("Migration file not found: %s", migration)
        _tables_initialized = True
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(migration.read_text())
    except sqlite3.OperationalError as exc:
        err_msg = str(exc).lower()
        if "duplicate column" in err_msg or "already exists" in err_msg:
            pass  # Expected when tables/columns already exist
        else:
            logger.warning("Migration error (non-fatal): %s", exc)
    conn.commit()
    conn.close()
    _tables_initialized = True


def pre_llm_call(
    messages: list[dict[str, Any]],
    model: str,
    step_name: str | None = None,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
    **kwargs: object,
) -> None:
    """Lifecycle hook — fires before every LLM call."""
    _ensure_tables()
    _call_start.set(time.monotonic())

    deliverable_id = get_deliverable_id()
    client_id = get_client_id()
    prompt_text = json.dumps(messages, ensure_ascii=False, default=str)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, pipeline_name, step_name,
            pipeline_version, model, prompt_text, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [deliverable_id, client_id, pipeline_name, step_name,
         pipeline_version, model or "unknown", prompt_text, time.time()],
    )
    _call_rowid.set(cursor.lastrowid)
    conn.commit()
    conn.close()


def post_llm_call(
    response_text: str | None = None,
    usage: dict[str, int] | None = None,
    **kwargs: object,
) -> None:
    """Lifecycle hook — fires after every LLM call."""
    rowid = _call_rowid.get()
    if rowid is None:
        return

    latency_ms = int((time.monotonic() - _call_start.get()) * 1000)
    input_tokens = usage.get("prompt_tokens", 0) if usage else 0
    output_tokens = usage.get("completion_tokens", 0) if usage else 0

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """UPDATE cost_ledger
           SET input_tokens = ?, output_tokens = ?, response_text = ?, latency_ms = ?
           WHERE id = ?""",
        [input_tokens, output_tokens, response_text, latency_ms, rowid],
    )
    conn.commit()
    conn.close()
    _call_rowid.set(None)


def record_quality(
    deliverable_id: str,
    quality_score: float,
    all_gates_passed: bool,
    layer_scores: dict[str, float] | None = None,
) -> None:
    """Record quality gate results for a deliverable.

    Args:
        deliverable_id: The deliverable ID.
        quality_score: Overall quality score.
        all_gates_passed: Whether all quality gates passed.
        layer_scores: Optional per-layer score breakdown.
    """
    _ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO quality_results
           (deliverable_id, quality_score, all_gates_passed, layer_scores_json, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        [
            deliverable_id,
            quality_score,
            1 if all_gates_passed else 0,
            json.dumps(layer_scores) if layer_scores else None,
            time.time(),
        ],
    )
    conn.commit()
    conn.close()


def update_baseline(
    pipeline_name: str,
    pipeline_version: str | None = None,
    bootstrap_count: int = 20,
) -> None:
    """Recalculate cost baseline for a pipeline from ledger data.

    Args:
        pipeline_name: Pipeline name to compute baseline for.
        pipeline_version: Optional version filter.
        bootstrap_count: Minimum samples before baseline is valid.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT SUM(input_tokens + output_tokens) AS total_tokens, deliverable_id
        FROM cost_ledger WHERE pipeline_name = ?
    """
    params: list[str | None] = [pipeline_name]
    if pipeline_version:
        query += " AND pipeline_version = ?"
        params.append(pipeline_version)
    query += " GROUP BY deliverable_id"

    rows = conn.execute(query, params).fetchall()
    if len(rows) < bootstrap_count:
        conn.close()
        return

    costs = [float(row["total_tokens"]) for row in rows]
    avg = sum(costs) / len(costs)
    variance = sum((c - avg) ** 2 for c in costs) / len(costs)
    stddev = math.sqrt(variance)

    conn.execute(
        """INSERT INTO cost_baselines
           (pipeline_name, pipeline_version, avg_cost, stddev, sample_count, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(pipeline_name, pipeline_version)
           DO UPDATE SET avg_cost = ?, stddev = ?, sample_count = ?, updated_at = ?""",
        [pipeline_name, pipeline_version, avg, stddev, len(costs), time.time(),
         avg, stddev, len(costs), time.time()],
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run tests and pyright**

Run: `pytest tests/middleware/test_cost_ledger.py -v && pyright middleware/cost_ledger.py`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git add middleware/cost_ledger.py tests/middleware/test_cost_ledger.py
git commit -m "feat: cost ledger lifecycle hook with ContextVar correlation"
```

---

## Chunk 3: Trace Exporter + Query Interface

### Task 6: Trace Exporter

**Files:**
- Create: `middleware/trace_exporter.py`
- Create: `tests/middleware/test_trace_exporter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/middleware/test_trace_exporter.py`:

```python
"""Tests for anomaly detection and trace export."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from middleware.deliverable_context import clear_context

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
        )
    """)
    sql = MIGRATION_PATH.read_text().replace(
        "ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;", ""
    )
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def traces_dir(tmp_path: Path) -> Path:
    d = tmp_path / "traces"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _patch(db_path: Path, traces_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("middleware.trace_exporter.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.trace_exporter.TRACES_DIR", str(traces_dir))
    clear_context()
    yield
    clear_context()


def _insert_cost(db_path: Path, deliverable_id: str, **overrides: object) -> None:
    defaults = {
        "client_id": "client_1", "pipeline_name": "content_generate",
        "step_name": "draft", "model": "gpt-5.4-mini",
        "input_tokens": 100, "output_tokens": 50,
        "prompt_text": '{"role":"user"}', "response_text": "resp",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, pipeline_name, step_name, model,
            input_tokens, output_tokens, prompt_text, response_text, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [deliverable_id, defaults["client_id"], defaults["pipeline_name"],
         defaults["step_name"], defaults["model"], defaults["input_tokens"],
         defaults["output_tokens"], defaults["prompt_text"],
         defaults["response_text"], time.time()],
    )
    conn.commit()
    conn.close()


def _insert_quality(db_path: Path, deliverable_id: str, score: float) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO quality_results (deliverable_id, quality_score, all_gates_passed, timestamp) VALUES (?, ?, ?, ?)",
        [deliverable_id, score, 1 if score >= 7.0 else 0, time.time()],
    )
    conn.commit()
    conn.close()


def _insert_baseline(db_path: Path, pipeline: str, avg: float, stddev: float) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO cost_baselines (pipeline_name, avg_cost, stddev, sample_count, updated_at) VALUES (?, ?, ?, ?, ?)",
        [pipeline, avg, stddev, 20, time.time()],
    )
    conn.commit()
    conn.close()


class TestCheckAnomalies:
    def test_detects_low_quality(self, db_path: Path) -> None:
        from middleware.trace_exporter import check_anomalies
        _insert_cost(db_path, "d-low-q")
        _insert_quality(db_path, "d-low-q", 5.0)
        result = check_anomalies("d-low-q")
        assert result["is_anomaly"] is True
        assert any("quality" in r.lower() for r in result["reasons"])

    def test_detects_high_cost(self, db_path: Path) -> None:
        from middleware.trace_exporter import check_anomalies
        _insert_baseline(db_path, "content_generate", avg=100.0, stddev=10.0)
        _insert_cost(db_path, "d-high-c", input_tokens=500, output_tokens=500)
        _insert_quality(db_path, "d-high-c", 8.0)
        result = check_anomalies("d-high-c")
        assert result["is_anomaly"] is True
        assert any("cost" in r.lower() for r in result["reasons"])

    def test_no_anomaly_when_normal(self, db_path: Path) -> None:
        from middleware.trace_exporter import check_anomalies
        _insert_baseline(db_path, "content_generate", avg=150.0, stddev=50.0)
        _insert_cost(db_path, "d-ok")
        _insert_quality(db_path, "d-ok", 8.0)
        result = check_anomalies("d-ok")
        assert result["is_anomaly"] is False


class TestExportTrace:
    def test_exports_json_file(self, db_path: Path, traces_dir: Path) -> None:
        from middleware.trace_exporter import export_trace
        _insert_cost(db_path, "d-export")
        path = export_trace("d-export")
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["deliverable_id"] == "d-export"
        assert len(data["steps"]) > 0
        assert "model" in data["steps"][0]
        assert "prompt_text" in data["steps"][0]


class TestLogAnomaly:
    def test_records_anomaly_in_db(self, db_path: Path) -> None:
        from middleware.trace_exporter import log_anomaly
        log_anomaly("d-anom", "client_1", "content_generate", ["quality too low"], "/traces/d-anom.json")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM anomaly_log WHERE deliverable_id = ?", ["d-anom"]).fetchone()
        conn.close()
        assert row is not None
        assert "quality" in json.loads(row["reasons_json"])[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/middleware/test_trace_exporter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement trace_exporter.py**

Create `middleware/trace_exporter.py`:

```python
"""Trace Exporter — anomaly detection, trace export, anomaly logging.

Checks deliverables against quality thresholds and cost baselines.
Exports full step-level traces as immutable JSON files.
Logs anomalies to anomaly_log table.
Notifies via Telegram if available (Gate 2 dependency).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from middleware.cost_config import load_config

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")
TRACES_DIR = "traces"


def check_anomalies(
    deliverable_id: str,
    quality_threshold: float | None = None,
    anomaly_stddev: float | None = None,
) -> dict[str, Any]:
    """Check if a deliverable has anomalies.

    Args:
        deliverable_id: The deliverable to check.
        quality_threshold: Override min quality score (default from config).
        anomaly_stddev: Override cost anomaly stddev multiplier (default from config).

    Returns:
        Dict with is_anomaly (bool), reasons (list[str]).
    """
    config = load_config()
    threshold = quality_threshold or config["quality"]["min_score"]
    stddev_mult = anomaly_stddev or config["baselines"]["anomaly_stddev"]

    reasons: list[str] = []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Quality check
    qr = conn.execute(
        "SELECT quality_score FROM quality_results WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    if qr and qr["quality_score"] is not None and qr["quality_score"] < threshold:
        reasons.append(f"Quality below threshold: {qr['quality_score']:.1f} < {threshold}")

    # Cost check against baselines
    cost_rows = conn.execute(
        """SELECT SUM(input_tokens + output_tokens) AS total_tokens, pipeline_name
           FROM cost_ledger WHERE deliverable_id = ? GROUP BY pipeline_name""",
        [deliverable_id],
    ).fetchall()

    for row in cost_rows:
        pipeline = row["pipeline_name"]
        total = row["total_tokens"]
        if pipeline is None:
            continue
        baseline = conn.execute(
            "SELECT avg_cost, stddev FROM cost_baselines WHERE pipeline_name = ?",
            [pipeline],
        ).fetchone()
        if baseline and baseline["stddev"] > 0:
            limit = baseline["avg_cost"] + stddev_mult * baseline["stddev"]
            if total > limit:
                reasons.append(f"Cost above baseline for {pipeline}: {total:.0f} > {limit:.0f}")

    conn.close()
    return {"is_anomaly": len(reasons) > 0, "reasons": reasons}


def export_trace(deliverable_id: str) -> str:
    """Export full trace as immutable JSON.

    Args:
        deliverable_id: The deliverable to export.

    Returns:
        Path to the exported trace file.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT model, pipeline_name, step_name, input_tokens, output_tokens,
                  prompt_text, response_text, latency_ms, timestamp
           FROM cost_ledger WHERE deliverable_id = ? ORDER BY timestamp""",
        [deliverable_id],
    ).fetchall()

    qr = conn.execute(
        "SELECT quality_score, all_gates_passed, layer_scores_json FROM quality_results WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    conn.close()

    steps = [dict(row) for row in rows]
    trace = {
        "deliverable_id": deliverable_id,
        "exported_at": time.time(),
        "steps": steps,
        "quality": {
            "score": qr["quality_score"] if qr else None,
            "all_gates_passed": bool(qr["all_gates_passed"]) if qr else None,
            "layer_scores": json.loads(qr["layer_scores_json"]) if qr and qr["layer_scores_json"] else None,
        },
        "total_tokens": sum(s["input_tokens"] + s["output_tokens"] for s in steps),
    }

    traces_path = Path(TRACES_DIR)
    traces_path.mkdir(parents=True, exist_ok=True)
    output_path = traces_path / f"{deliverable_id}.json"
    output_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False))
    return str(output_path)


def log_anomaly(
    deliverable_id: str,
    client_id: str | None,
    pipeline_name: str | None,
    reasons: list[str],
    trace_path: str | None,
) -> None:
    """Record anomaly in anomaly_log table.

    Args:
        deliverable_id: The deliverable with anomaly.
        client_id: Client identifier.
        pipeline_name: Pipeline that produced the deliverable.
        reasons: List of anomaly reasons.
        trace_path: Path to exported trace file.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO anomaly_log
           (deliverable_id, client_id, pipeline_name, reasons_json, trace_path, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [deliverable_id, client_id, pipeline_name,
         json.dumps(reasons), trace_path, time.time()],
    )
    conn.commit()
    conn.close()


def notify_anomaly(
    deliverable_id: str,
    client_id: str | None,
    pipeline_name: str | None,
    reasons: list[str],
    trace_path: str | None,
) -> None:
    """Send Telegram notification for anomaly. Graceful fallback if Gate 2 not deployed.

    Args:
        deliverable_id: The deliverable with anomaly.
        client_id: Client identifier.
        pipeline_name: Pipeline name.
        reasons: List of anomaly reasons.
        trace_path: Path to trace file.
    """
    message = (
        f"Anomaly detected: {deliverable_id}\n"
        f"Client: {client_id or 'unknown'}\n"
        f"Pipeline: {pipeline_name or 'unknown'}\n"
        f"Reasons: {'; '.join(reasons)}\n"
        f"Trace: {trace_path or 'N/A'}"
    )
    try:
        from scripts.delivery.send_telegram import send_telegram  # type: ignore[import-not-found]
        send_telegram(message)
    except ImportError:
        logger.info("Telegram not available (Gate 2). Anomaly logged: %s", deliverable_id)


def cleanup_traces(retention_days: int | None = None) -> int:
    """Archive traces older than retention period.

    Args:
        retention_days: Override retention period (default from config).

    Returns:
        Number of traces archived.
    """
    config = load_config()
    days = retention_days or config["traces"]["retention_days"]
    archive_dir = Path(config["traces"]["archive_dir"])
    traces_dir = Path(TRACES_DIR)

    if not traces_dir.exists():
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - (days * 86400)
    archived = 0

    for trace_file in traces_dir.glob("*.json"):
        if trace_file.stat().st_mtime < cutoff:
            trace_file.rename(archive_dir / trace_file.name)
            archived += 1

    if archived:
        logger.info("Archived %d traces older than %d days", archived, days)
    return archived
```

- [ ] **Step 4: Run tests and pyright**

Run: `pytest tests/middleware/test_trace_exporter.py -v && pyright middleware/trace_exporter.py`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git add middleware/trace_exporter.py tests/middleware/test_trace_exporter.py
git commit -m "feat: anomaly detection, trace export, and anomaly logging"
```

---

### Task 7: Query Costs Tool

**Files:**
- Create: `tools/query_costs.py`
- Create: `tests/tools/test_query_costs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/tools/test_query_costs.py`:

```python
"""Tests for query_costs tool."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_with_costs(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
        )
    """)
    sql = MIGRATION_PATH.read_text().replace(
        "ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;", ""
    )
    conn.executescript(sql)

    now = time.time()
    conn.executemany(
        """INSERT INTO cost_ledger
           (deliverable_id, client_id, model, pipeline_name, step_name,
            input_tokens, output_tokens, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("d1", "client_a", "gpt-5.4-mini", "content_generate", "draft", 100, 50, now),
            ("d1", "client_a", "gpt-5.4-mini", "content_generate", "format", 20, 10, now),
            ("d2", "client_b", "qwen3.5:9b", "content_generate", "draft", 200, 100, now),
        ],
    )
    # Insert an anomaly log entry
    conn.execute(
        "INSERT INTO anomaly_log (deliverable_id, client_id, pipeline_name, reasons_json, timestamp) VALUES (?, ?, ?, ?, ?)",
        ["d1", "client_a", "content_generate", '["quality low"]', now],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _patch_db(db_with_costs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.query_costs.DB_PATH", str(db_with_costs))


class TestQueryCosts:
    def test_per_deliverable(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"deliverable_id": "d1"}))
        assert len(result["steps"]) == 2
        assert result["total_tokens"] == 180

    def test_per_client(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"client_id": "client_a"}))
        assert len(result["deliverables"]) == 1

    def test_model_distribution(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"distribution": True}))
        assert "gpt-5.4-mini" in result["models"]
        assert "qwen3.5:9b" in result["models"]

    def test_anomaly_history(self) -> None:
        from tools.query_costs import query_costs
        result = json.loads(query_costs({"anomaly_history": True}))
        assert "anomalies" in result
        assert len(result["anomalies"]) == 1

    def test_handles_missing_table(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from tools.query_costs import query_costs
        empty_db = tmp_path / "empty.db"
        sqlite3.connect(str(empty_db)).close()
        monkeypatch.setattr("tools.query_costs.DB_PATH", str(empty_db))
        result = json.loads(query_costs({}))
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/tools/test_query_costs.py -v`
Expected: FAIL

- [ ] **Step 3: Implement query_costs.py**

Create `tools/query_costs.py`:

```python
"""Query Costs — model-callable Hermes tool for cost self-inspection."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from middleware.cost_config import calculate_cost

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".hermes" / "state.db")


def query_costs(args: dict[str, Any], **kw: Any) -> str:
    """Query cost ledger data.

    Args:
        args: Dict with optional keys:
            - deliverable_id: Per-deliverable step breakdown
            - client_id: Per-client rollup
            - distribution: Model token distribution
            - anomaly_history: Recent anomalies
            - top_steps: Most expensive steps (default 10)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if args.get("deliverable_id"):
            return _per_deliverable(conn, args["deliverable_id"])
        if args.get("client_id"):
            return _per_client(conn, args["client_id"])
        if args.get("distribution"):
            return _model_distribution(conn)
        if args.get("anomaly_history"):
            return _anomaly_history(conn, args.get("limit", 50))
        return _top_expensive_steps(conn, args.get("top_steps", 10))

    except sqlite3.OperationalError as exc:
        return json.dumps({"error": f"Database error: {exc}"})


def _per_deliverable(conn: sqlite3.Connection, deliverable_id: str) -> str:
    rows = conn.execute(
        """SELECT step_name, model, input_tokens, output_tokens, latency_ms
           FROM cost_ledger WHERE deliverable_id = ? ORDER BY timestamp""",
        [deliverable_id],
    ).fetchall()
    conn.close()
    steps = [dict(row) for row in rows]
    total = sum(s["input_tokens"] + s["output_tokens"] for s in steps)
    total_cost = sum(calculate_cost(s["model"], s["input_tokens"], s["output_tokens"]) for s in steps)
    return json.dumps({"deliverable_id": deliverable_id, "steps": steps,
                       "total_tokens": total, "total_cost": total_cost})


def _per_client(conn: sqlite3.Connection, client_id: str) -> str:
    rows = conn.execute(
        """SELECT deliverable_id, SUM(input_tokens + output_tokens) AS total_tokens, COUNT(*) AS step_count
           FROM cost_ledger WHERE client_id = ?
           GROUP BY deliverable_id ORDER BY MIN(timestamp) DESC""",
        [client_id],
    ).fetchall()
    conn.close()
    return json.dumps({"client_id": client_id, "deliverables": [dict(r) for r in rows]})


def _model_distribution(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """SELECT model, SUM(input_tokens) AS total_in, SUM(output_tokens) AS total_out, COUNT(*) AS call_count
           FROM cost_ledger GROUP BY model""",
    ).fetchall()
    conn.close()
    models = {row["model"]: {"input": row["total_in"], "output": row["total_out"], "calls": row["call_count"]} for row in rows}
    return json.dumps({"models": models})


def _anomaly_history(conn: sqlite3.Connection, limit: int) -> str:
    rows = conn.execute(
        """SELECT deliverable_id, client_id, pipeline_name, reasons_json, trace_path, timestamp
           FROM anomaly_log ORDER BY timestamp DESC LIMIT ?""",
        [limit],
    ).fetchall()
    conn.close()
    anomalies = [
        {**dict(row), "reasons": json.loads(row["reasons_json"])}
        for row in rows
    ]
    return json.dumps({"anomalies": anomalies})


def _top_expensive_steps(conn: sqlite3.Connection, limit: int) -> str:
    rows = conn.execute(
        """SELECT step_name, SUM(input_tokens + output_tokens) AS total_tokens,
                  COUNT(*) AS run_count, AVG(input_tokens + output_tokens) AS avg_tokens
           FROM cost_ledger WHERE step_name IS NOT NULL
           GROUP BY step_name ORDER BY total_tokens DESC LIMIT ?""",
        [limit],
    ).fetchall()
    conn.close()
    return json.dumps({"top_steps": [dict(r) for r in rows]})


def register_query_costs_tool() -> None:
    """Register query_costs as a Hermes tool."""
    try:
        from tools.registry import registry  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("Hermes registry not available — query_costs not registered")
        return

    registry.register(
        name="query_costs",
        toolset="vizier-core",
        schema={
            "type": "object",
            "properties": {
                "deliverable_id": {"type": "string", "description": "Step-level cost breakdown for a deliverable"},
                "client_id": {"type": "string", "description": "Cost rollup for a client"},
                "distribution": {"type": "boolean", "description": "Token distribution by model"},
                "anomaly_history": {"type": "boolean", "description": "Recent anomaly log entries"},
                "top_steps": {"type": "integer", "description": "N most expensive steps (default 10)"},
            },
            "required": [],
        },
        handler=query_costs,
        check_fn=lambda: True,
        description="Inspect cost ledger: per-deliverable, per-client, model distribution, anomaly history, top expensive steps",
    )
```

- [ ] **Step 4: Run tests and pyright**

Run: `pytest tests/tools/test_query_costs.py -v && pyright tools/query_costs.py`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git add tools/query_costs.py tests/tools/test_query_costs.py
git commit -m "feat: query_costs tool with anomaly history and model distribution"
```

---

## Chunk 4: Integration + Coverage

### Task 8: Integration Test

**Files:**
- Create: `tests/test_track1_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_track1_integration.py`:

```python
"""Integration test — full Track 1 flow: context → ledger → quality → anomaly → export → query."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from middleware.deliverable_context import clear_context, start_deliverable

MIGRATION_PATH = Path(__file__).parent.parent / "migrations" / "001_cost_ledger.sql"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, step INTEGER, model TEXT,
            messages_json TEXT, tools_json TEXT, timestamp REAL,
            tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
            deliverable_id TEXT
        )
    """)
    sql = MIGRATION_PATH.read_text().replace(
        "ALTER TABLE prompt_log ADD COLUMN deliverable_id TEXT;", ""
    )
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def traces_dir(tmp_path: Path) -> Path:
    d = tmp_path / "traces"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _patch_all(db_path: Path, traces_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("middleware.cost_ledger.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.cost_ledger._tables_initialized", True)
    monkeypatch.setattr("middleware.trace_exporter.DB_PATH", str(db_path))
    monkeypatch.setattr("middleware.trace_exporter.TRACES_DIR", str(traces_dir))
    monkeypatch.setattr("tools.query_costs.DB_PATH", str(db_path))
    clear_context()
    yield
    clear_context()


class TestTrack1EndToEnd:
    def test_full_flow(self, db_path: Path, traces_dir: Path) -> None:
        from middleware.cost_ledger import post_llm_call, pre_llm_call, record_quality
        from middleware.trace_exporter import check_anomalies, export_trace, log_anomaly
        from tools.query_costs import query_costs

        # 1. Start deliverable
        did = start_deliverable(client_id="acme_corp")

        # 2. Simulate pipeline (2 LLM calls)
        pre_llm_call(
            messages=[{"role": "user", "content": "Write copy"}],
            model="gpt-5.4-mini",
            step_name="draft",
            pipeline_name="content_generate",
            pipeline_version="1.0",
        )
        post_llm_call(
            response_text="Here is your copy...",
            usage={"prompt_tokens": 150, "completion_tokens": 200},
        )

        pre_llm_call(
            messages=[{"role": "user", "content": "Format"}],
            model="gpt-5.4-mini",
            step_name="format",
            pipeline_name="content_generate",
            pipeline_version="1.0",
        )
        post_llm_call(
            response_text="Formatted.",
            usage={"prompt_tokens": 50, "completion_tokens": 30},
        )

        # 3. Record quality (low → triggers anomaly)
        record_quality(did, quality_score=5.5, all_gates_passed=False)

        # 4. Check anomalies
        result = check_anomalies(did)
        assert result["is_anomaly"] is True

        # 5. Export trace + log anomaly
        trace_path = export_trace(did)
        log_anomaly(did, "acme_corp", "content_generate", result["reasons"], trace_path)
        trace = json.loads(Path(trace_path).read_text())
        assert len(trace["steps"]) == 2
        assert trace["quality"]["score"] == 5.5

        # 6. Query costs
        breakdown = json.loads(query_costs({"deliverable_id": did}))
        assert breakdown["total_tokens"] == 430

        client = json.loads(query_costs({"client_id": "acme_corp"}))
        assert len(client["deliverables"]) == 1

        anomalies = json.loads(query_costs({"anomaly_history": True}))
        assert len(anomalies["anomalies"]) == 1
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_track1_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full suite with coverage**

Run: `pytest --cov=middleware --cov=tools --cov=plugins --cov-report=term-missing -v`
Expected: All pass, 80%+ coverage on new modules

- [ ] **Step 4: Lint and format**

Run: `ruff check --fix middleware/ tools/ plugins/context_injector.py && black middleware/ tools/ plugins/context_injector.py`
Expected: Clean

- [ ] **Step 5: Commit**

```bash
git add tests/test_track1_integration.py
git commit -m "test: Track 1 end-to-end integration — context, ledger, anomaly, query"
```
