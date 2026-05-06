# Phase 2 — PNC Parser End-to-End

**Prerequisites:** Phase 1 complete and verified.

## Goal

Build the first real parser end-to-end: read a PNC checking CSV, normalize it, write rows to both `raw_transactions` and `transactions`. PNC is first because it's the most varied source (paychecks, expenses, transfers, payments), and solving it first surfaces design problems while the rest of the codebase is still small.

By the end of this phase, `budget ingest tests/fixtures/sample_pnc.csv --source pnc` should work end-to-end and be idempotent.

## Step 1: Read the fixture before writing any code

Read `tests/fixtures/sample_pnc.csv` fully. Note:

- Exact column names and order
- Date format(s) — does PNC use one column or two (transaction date vs post date)?
- How are credits and debits represented? Single signed column? Separate Debit/Credit columns? "Amount" + "Type"?
- Are there header lines, blank rows, or footer summary rows?
- What categories does PNC provide, if any?
- Does the description field include merchant info, transfer notes, check numbers?
- What does a paycheck look like? An ACH transfer out to Fidelity? A credit card payment?
- Encoding (likely UTF-8 but check; some banks use Windows-1252)

**Write down what you observe in a comment at the top of `src/budgeting/parsers/pnc.py` before writing the parser.** This documents the contract for future-you.

If anything is ambiguous or the fixture is missing an example you'd expect (e.g., no paycheck row visible), stop and ask me before proceeding.

## Step 2: Implement `PNCParser`

In `src/budgeting/parsers/pnc.py`:

- Subclass `BaseParser`
- Set `account_source = "pnc"`, `account_type = "checking"`
- Implement `parse(csv_path)` to yield `NormalizedTransaction` objects
- Use `csv.DictReader` for parsing
- Convert amounts to `Decimal` (never `float` — floating point and money don't mix)
- Sign convention: negative for money leaving the account, positive for money arriving
- Parse dates with explicit formats; raise on unparseable
- For `transaction_id`, track an occurrence counter for same-day + same-amount + same-description rows so duplicates within a single day still get distinct IDs
- Set `category_source` from PNC's category column if present, else `None`
- Do not categorize, do not detect transfers, do not clean merchants — those are later phases

## Step 3: Wire ingestion into the CLI

Implement `budget ingest <csv_path> --source <source>` properly now:

1. Look up the parser class from a registry: `{"pnc": PNCParser, "fidelity": FidelityParser, ...}` — register the others as `None` for now and raise a clear "not yet implemented" error if selected
2. Open a DB connection, start a transaction
3. Insert an `ingestion_runs` row with status `'started'` (use `started_at`)
4. For each `NormalizedTransaction` yielded:
   - Insert into `raw_transactions` (json-encode `raw_payload`); if `(account_source, source_file, row_number)` already exists, skip
   - Insert into `transactions`; if `transaction_id` already exists, skip (this is the idempotency guarantee)
   - Track inserted vs skipped counts
5. Update the `ingestion_runs` row with `completed_at`, status, counts
6. Commit (or rollback on exception, mark run as `'failed'` with the error message)
7. Print a summary: `"PNC: read 47 rows, inserted 47, skipped 0"`

Also archive the source file: copy it into `data/raw/pnc/` with a timestamped filename (e.g., `pnc_2026-05-05_<original_name>.csv`). The `source_file` column should reference this archived path, not the user's original input path.

## Step 4: Tests

`tests/test_pnc_parser.py`:

- Parses `tests/fixtures/sample_pnc.csv` without error
- Yields the expected number of `NormalizedTransaction` objects
- Spot-check a few specific rows: a paycheck (positive amount), an expense (negative), a transfer out (negative)
- All amounts are `Decimal`, all dates are `date` objects
- `transaction_id` values are unique within the run
- Re-running the parser on the same file produces the same `transaction_id`s (deterministic)

`tests/test_pnc_ingest.py`:

- End-to-end: `budget ingest tests/fixtures/sample_pnc.csv --source pnc` against an in-memory or temp-file DB
- Verify counts in `raw_transactions` and `transactions` match
- Run the same command twice; second run inserts zero new rows (idempotency)
- `ingestion_runs` has a row with status `'success'`

## Definition of done

- [ ] `tests/fixtures/sample_pnc.csv` documented in a header comment in the parser
- [ ] `PNCParser.parse()` produces correct `NormalizedTransaction` objects
- [ ] CLI ingest command works against the fixture
- [ ] Re-running ingestion is idempotent
- [ ] Source file is archived to `data/raw/pnc/`
- [ ] All tests pass
- [ ] No transfer detection, no categorization (those are later phases)

## Stop here

Summarize the PNC CSV format you discovered, show me one example normalized row, and wait for me to verify before Phase 3.
