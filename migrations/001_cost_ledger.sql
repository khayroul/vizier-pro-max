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
