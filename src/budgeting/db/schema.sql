-- Bronze layer: every CSV row preserved as-is
CREATE TABLE IF NOT EXISTS raw_transactions (
    raw_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_source  TEXT NOT NULL,           -- 'pnc', 'fidelity', 'amex', 'discover', 'capital_one'
    source_file     TEXT NOT NULL,           -- relative path of the CSV ingested
    row_number      INTEGER NOT NULL,        -- 1-indexed row in the source file
    raw_payload     TEXT NOT NULL,           -- JSON of the original row {column: value}
    ingested_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_source, source_file, row_number)
);

CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_transactions(account_source);
CREATE INDEX IF NOT EXISTS idx_raw_file ON raw_transactions(source_file);

-- Silver layer: normalized, unified schema
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      TEXT PRIMARY KEY,    -- deterministic hash, see README
    raw_id              INTEGER NOT NULL,
    account_source      TEXT NOT NULL,       -- 'pnc', 'fidelity', 'amex', 'discover', 'capital_one'
    account_type        TEXT NOT NULL,       -- 'checking', 'investment', 'credit_card'
    transaction_date    DATE NOT NULL,
    post_date           DATE,                -- nullable
    description_raw     TEXT NOT NULL,
    merchant_clean      TEXT,                -- populated by gold layer
    amount              DECIMAL(12,2) NOT NULL,  -- signed: negative=outflow, positive=inflow
    category_source     TEXT,                -- whatever the bank called it
    category_unified    TEXT,                -- our taxonomy, populated by gold layer
    subcategory         TEXT,                -- populated by gold layer
    is_transfer         BOOLEAN NOT NULL DEFAULT 0,
    is_pending          BOOLEAN NOT NULL DEFAULT 0,
    ingested_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raw_id) REFERENCES raw_transactions(raw_id)
);

CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_tx_source ON transactions(account_source);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_unified);
CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(is_transfer);

-- Categorization rules, evaluated in priority order (lower = higher priority)
CREATE TABLE IF NOT EXISTS categorization_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    priority            INTEGER NOT NULL,
    pattern             TEXT NOT NULL,       -- regex matched against description_raw
    account_source      TEXT,                -- nullable; null = applies to all sources
    category_unified    TEXT NOT NULL,
    subcategory         TEXT,
    merchant_clean      TEXT,                -- optional canonical merchant name
    notes               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rules_priority ON categorization_rules(priority);

-- Detected transfer pairs (PNC->Fidelity, PNC->Amex payment, etc.)
CREATE TABLE IF NOT EXISTS transfer_pairs (
    pair_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    outflow_tx_id       TEXT NOT NULL,
    inflow_tx_id        TEXT NOT NULL,
    detected_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detection_method    TEXT NOT NULL,       -- 'amount_date_match', 'manual', etc.
    FOREIGN KEY (outflow_tx_id) REFERENCES transactions(transaction_id),
    FOREIGN KEY (inflow_tx_id) REFERENCES transactions(transaction_id),
    UNIQUE(outflow_tx_id, inflow_tx_id)
);

-- Ingestion run log for debugging
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_source      TEXT NOT NULL,
    source_file         TEXT NOT NULL,
    rows_read           INTEGER NOT NULL,
    rows_inserted       INTEGER NOT NULL,
    rows_skipped        INTEGER NOT NULL,    -- duplicates
    started_at          TIMESTAMP NOT NULL,
    completed_at        TIMESTAMP,
    status              TEXT NOT NULL,       -- 'success', 'failed', 'partial'
    error_message       TEXT
);
