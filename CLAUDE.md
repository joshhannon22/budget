# Personal Finance Pipeline — Project Brief

You are helping me build a personal finance data pipeline in Python. This document is the canonical project brief. Read it fully before starting any phase.

## What we're building

A medallion-architecture data pipeline that ingests CSV exports from five financial accounts, normalizes them into a unified schema, applies consistent categorization, and stores everything in SQLite for analysis and (eventually) dashboarding.

This is a personal project, run locally, single-user. Optimize for clarity and maintainability over enterprise concerns.

## My accounts

| Source | Type | Volume | Notes |
|---|---|---|---|
| PNC | Checking | Medium | Paycheck deposits, cash expenses, transfers out to Fidelity, credit card payments |
| Fidelity | Investment | Low | Mostly transfers in from PNC, money market positions, dividends/interest |
| American Express | Credit Card | High | Primary daily-spend card, cashback credits, monthly autopay from PNC |
| Discover | Credit Card | Very Low | 1–3 transactions/month |
| Capital One | Credit Card | Very Low | Even fewer transactions than Discover |

## Architecture: medallion pipeline

Three layers, each with a clear responsibility:

**Bronze (raw):** Every CSV ingested gets archived as-is and loaded into a `raw_transactions` table preserving the original row. Never mutated. Source of truth for re-runs.

**Silver (normalized):** A single `transactions` table where every account conforms to the same schema. Account-specific parsers handle the translation.

**Gold (enriched):** The same transactions with unified categories applied, merchant names cleaned, and internal transfers flagged so they don't double-count as spending.

Downstream analysis and dashboards read from the gold layer.

## Tech stack

- **Python 3.11+**
- **SQLite** for storage (single file, zero setup, scales fine for personal use; schema designed to migrate to Postgres later if needed)
- **Pydantic v2** for the normalized transaction model and validation
- **Typer** for the CLI
- **PyYAML** for editable categorization rules
- **pytest** for tests
- **uv** or **pip** + `pyproject.toml` for dependency management — your choice, but commit a lockfile
- Standard library `sqlite3` is fine; do not pull in SQLAlchemy unless a phase explicitly calls for it

No external services. No cloud. No API keys. CSV in, SQLite out.

## Project structure

```
~/dev/budgeting/
├── pyproject.toml
├── README.md
├── docs/
│   └── phases/                     # phase-by-phase build instructions
├── data/
│   ├── raw/                        # archived CSV exports, organized by source/date
│   │   ├── pnc/
│   │   ├── fidelity/
│   │   ├── amex/
│   │   ├── discover/
│   │   └── capital_one/
│   └── budgeting.db                # SQLite database (gitignored)
├── src/budgeting/
│   ├── __init__.py
│   ├── db/
│   │   ├── schema.sql
│   │   ├── connection.py
│   │   └── migrations/
│   ├── parsers/
│   │   ├── base.py
│   │   ├── pnc.py
│   │   ├── fidelity.py
│   │   ├── amex.py
│   │   ├── discover.py
│   │   └── capital_one.py
│   ├── categorization/
│   │   ├── rules.py
│   │   ├── rules.yaml
│   │   └── transfer_detection.py
│   ├── models.py                   # Pydantic models
│   ├── ingest.py                   # orchestrator
│   └── cli.py                      # Typer CLI
├── tests/
│   ├── fixtures/                   # sanitized sample CSVs per source
│   └── test_*.py
└── notebooks/                      # ad-hoc analysis
```

## Sample data convention

Sanitized sample exports from each account live at:

```
tests/fixtures/sample_pnc.csv
tests/fixtures/sample_fidelity.csv
tests/fixtures/sample_amex.csv
tests/fixtures/sample_discover.csv
tests/fixtures/sample_capital_one.csv
```

**Always read the relevant fixture file before writing or modifying a parser.** The CSV format quirks of each source (column names, date formats, signed vs unsigned amounts, header/footer rows, encoding) are not described in prose — they're in the file. Inspect the file first, write the parser second.

These fixtures double as test inputs for the parser test suite.

## Build order

The project is broken into phases. Each phase has its own document under `docs/phases/`. Complete and verify each phase before moving to the next:

1. `phase_01_scaffold.md` — Project setup, schema, base parser contract, CLI skeleton
2. `phase_02_pnc_parser.md` — PNC parser end-to-end (most complex source; surfaces design issues early)
3. `phase_03_amex_parser.md` — Amex parser (highest volume, most categorization rules)
4. `phase_04_remaining_parsers.md` — Discover, Capital One, Fidelity parsers
5. `phase_05_categorization.md` — Rules engine and initial rules.yaml
6. `phase_06_transfer_detection.md` — Internal transfer matching
7. `phase_07_views_and_queries.md` — SQL views for common analytical questions

Do not skip ahead. Each phase assumes the previous one is complete and tested.

## Working agreements

- **Idempotent ingestion.** Re-running the same CSV must not create duplicate rows. Use a deterministic `transaction_id` derived from `hash(source + date + amount + description + occurrence_index)`.
- **Signed amounts.** Every parser outputs `amount` as a signed `Decimal`: negative for outflows (expenses, transfers out), positive for inflows (income, refunds, transfers in). No exceptions.
- **Preserve raw data.** Never modify or drop rows from `raw_transactions`. All cleanup happens downstream.
- **Fail loudly on unknowns.** If a parser sees a column it doesn't recognize or a date it can't parse, raise — don't silently coerce. Better to fix the parser than carry bad data.
- **Tests required.** Every parser ships with tests using its fixture file. Categorization rules ship with tests. No "I'll test it later."
- **Ask before assuming.** If a fixture file is missing or ambiguous, stop and ask me rather than inventing a format.

## Out of scope (for now)

- Web dashboards / visualization (separate project after this is stable)
- LLM-based categorization (deterministic rules first; LLM layer comes later if needed)
- Real-time bank API integrations (Plaid, etc.) — CSV export only
- Multi-user support
- Cloud sync

Keep these out of the design. Don't add abstractions "in case" we need them later.
