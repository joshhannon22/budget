# Phase 1 — Project Scaffold, Schema, and Base Parser Contract

**Prerequisites:** Read `CLAUDE.md` first.

## Goal

Stand up the project skeleton, the SQLite schema, the abstract parser contract, and a CLI skeleton. No actual parsing logic yet — this phase is pure plumbing. By the end, I should be able to run `budget --help` and see commands, and run a migration that creates an empty database with the right tables.

## Deliverables

1. `pyproject.toml` with dependencies pinned
2. `src/budgeting/` package with the structure described in the README
3. `src/budgeting/db/schema.sql` with the full schema below
4. `src/budgeting/db/connection.py` — a single `get_connection()` helper that returns a `sqlite3.Connection` with `row_factory = sqlite3.Row` and foreign keys enabled
5. `src/budgeting/models.py` — Pydantic models for `RawTransaction` and `NormalizedTransaction`
6. `src/budgeting/parsers/base.py` — abstract base class all parsers inherit from
7. `src/budgeting/cli.py` — Typer CLI with stub commands: `init-db`, `ingest`, `list-sources`
8. `.gitignore` covering `data/budgeting.db`, `data/raw/*` (but keep the directory structure with `.gitkeep` files), `__pycache__`, `.venv`, `*.egg-info`
9. `tests/test_schema.py` — verifies migration runs cleanly and creates expected tables

## Schema

Write this exactly to `src/budgeting/db/schema.sql`:

```sql
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
```

## Pydantic models

In `src/budgeting/models.py`:

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

class NormalizedTransaction(BaseModel):
    """The contract every parser must produce."""
    transaction_id: str          # deterministic hash
    account_source: str          # 'pnc', 'fidelity', 'amex', 'discover', 'capital_one'
    account_type: str            # 'checking', 'investment', 'credit_card'
    transaction_date: date
    post_date: Optional[date] = None
    description_raw: str
    amount: Decimal              # signed: negative=outflow, positive=inflow
    category_source: Optional[str] = None
    is_pending: bool = False
    raw_payload: dict            # original CSV row as dict, for raw_transactions storage
    source_file: str             # relative path
    row_number: int              # 1-indexed row in source file

    model_config = {"arbitrary_types_allowed": True}
```

## Base parser contract

In `src/budgeting/parsers/base.py`:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator
from budgeting.models import NormalizedTransaction

class BaseParser(ABC):
    """Abstract parser. Each account-specific parser implements parse()."""

    account_source: str = ""     # subclass must set
    account_type: str = ""       # subclass must set

    @abstractmethod
    def parse(self, csv_path: Path) -> Iterator[NormalizedTransaction]:
        """Yield NormalizedTransaction objects, one per CSV row.

        Implementations must:
        - Sign amounts correctly (negative=outflow, positive=inflow)
        - Generate a deterministic transaction_id
        - Preserve the original row as raw_payload (dict)
        - Raise on unrecognized columns or unparseable dates
        """
        ...

    @staticmethod
    def make_transaction_id(
        account_source: str,
        transaction_date: str,
        amount: str,
        description: str,
        occurrence_index: int = 0,
    ) -> str:
        """Stable hash so re-imports are idempotent.

        occurrence_index disambiguates same-day same-amount duplicates
        (e.g. two $5.00 coffees on the same day at the same shop).
        """
        import hashlib
        key = f"{account_source}|{transaction_date}|{amount}|{description}|{occurrence_index}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
```

## CLI skeleton

In `src/budgeting/cli.py`, use Typer. Stubs only — actual ingestion logic comes in later phases. Commands:

- `budget init-db` — runs `schema.sql` against `data/budgeting.db`
- `budget ingest <csv_path> --source <source_name>` — placeholder, just prints "not yet implemented"
- `budget list-sources` — prints the five known sources

Wire up `pyproject.toml` so `pip install -e .` produces a `budget` console script.

## Tests for this phase

`tests/test_schema.py` should:

1. Create a fresh in-memory SQLite database
2. Run `schema.sql`
3. Assert all expected tables exist (`raw_transactions`, `transactions`, `categorization_rules`, `transfer_pairs`, `ingestion_runs`)
4. Assert expected indexes exist
5. Assert that inserting a row into `transactions` with a non-existent `raw_id` fails (foreign keys enforced)

## Definition of done

- [ ] `pip install -e .` succeeds
- [ ] `budget init-db` creates `data/budgeting.db` with all tables
- [ ] `budget --help` lists commands
- [ ] `pytest` passes
- [ ] `data/raw/{pnc,fidelity,amex,discover,capital_one}/.gitkeep` files exist
- [ ] No parser implementations yet (those are later phases)

## Stop here

When done, summarize what you built and wait for me to verify before starting Phase 2.
