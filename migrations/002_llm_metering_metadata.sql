-- Track 1 extension: richer LLM metering metadata
-- Additive only — does not drop or modify existing data

ALTER TABLE cost_ledger ADD COLUMN provider_name TEXT;
ALTER TABLE cost_ledger ADD COLUMN source TEXT;
ALTER TABLE cost_ledger ADD COLUMN modality TEXT DEFAULT 'chat';
ALTER TABLE cost_ledger ADD COLUMN status TEXT DEFAULT 'succeeded';
ALTER TABLE cost_ledger ADD COLUMN failure_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_cost_ledger_provider
    ON cost_ledger(provider_name);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_source
    ON cost_ledger(source);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_status
    ON cost_ledger(status);
