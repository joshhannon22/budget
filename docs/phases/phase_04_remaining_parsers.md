# Phase 4 — Discover, Capital One, and Fidelity Parsers

**Prerequisites:** Phases 1–3 complete. PNC and Amex ingesting cleanly.

## Goal

Add the remaining three parsers. By the end of this phase, all five sources can be ingested via the CLI, and the database holds a complete picture of activity across every account.

These are smaller, lower-volume sources. They follow the same pattern established by PNC and Amex — there should be very little new design here.

## Order of work

Do them in this order:

1. **Discover** — straightforward credit card, similar to Amex
2. **Capital One** — straightforward credit card, similar to Amex
3. **Fidelity** — investment account; needs the most thought

For each one:

1. Read the fixture (`tests/fixtures/sample_<source>.csv`)
2. Document the format at the top of the parser file
3. Subclass `BaseParser`
4. Handle the source's sign convention — flip if needed to match our internal "negative=outflow" rule
5. Register the parser in the CLI registry
6. Write tests against the fixture
7. Run end-to-end ingestion
8. Verify with the cross-source sanity query from Phase 3

## Discover (`src/budgeting/parsers/discover.py`)

- `account_source = "discover"`, `account_type = "credit_card"`
- Likely similar to Amex: purchases positive, payments/credits negative — flip to match our convention
- Discover provides a `Category` column; populate `category_source`
- Confirm sign convention from the fixture before assuming

## Capital One (`src/budgeting/parsers/capital_one.py`)

- `account_source = "capital_one"`, `account_type = "credit_card"`
- Capital One historically uses **separate** Debit and Credit columns (no signed amount). Confirm against the fixture. If true:
  - Compute `amount = -(debit_value) + (credit_value)` so debits are negative and credits positive
  - Exactly one of the two should be populated per row; if both are populated or both empty, raise
- Capital One also provides a `Category` column; populate `category_source`

## Fidelity (`src/budgeting/parsers/fidelity.py`)

This is the most different from the others — it's an investment account, not a transaction account. Read the fixture carefully.

- `account_source = "fidelity"`, `account_type = "investment"`
- Fidelity exports include things that don't fit the "spending transaction" model cleanly:
  - Cash transfers in (from PNC) — store as positive amount
  - Cash transfers out (to PNC) — store as negative amount
  - Buy/sell of securities — these are not "spending"; they reshuffle dollars within the account
  - Dividends and interest — positive (income)
  - Money market position changes (FDRXX, SPAXX, etc.)
- For this phase, ingest **all** rows from the Fidelity export into `raw_transactions` (preserve everything), but in `transactions`, only emit rows that represent actual cash flow into or out of the account from outside it. Specifically:
  - **Include:** External transfers in/out, dividends, interest, fees
  - **Exclude:** Internal buys/sells where money stays inside Fidelity (we still store these in `raw_transactions` for completeness; we just don't surface them in the silver layer)
- Document this filtering decision clearly in the parser header
- If the fixture doesn't make the distinction obvious, stop and ask me

## Tests

For each parser, follow the pattern from Phase 2/3:

- `tests/test_<source>_parser.py` — parses fixture, yields expected count, sign convention correct, deterministic IDs
- For Capital One specifically, test the debit/credit column merge logic
- For Fidelity, test that internal buy/sell rows are excluded from `NormalizedTransaction` output but **are** present in `raw_transactions` after ingestion

## Final cross-source check

After all five sources are ingested, run:

```sql
SELECT account_source, account_type,
       COUNT(*) as n,
       SUM(amount) as net_flow,
       MIN(transaction_date) as earliest,
       MAX(transaction_date) as latest
FROM transactions
GROUP BY account_source, account_type
ORDER BY account_source;
```

Sanity-check the net flows:

- Credit cards (Amex, Discover, Cap One): net should be ~0 if you paid them off in the period (purchases roughly equal payments). Substantially negative net = unpaid balance accruing.
- PNC: net depends on whether you saved money in the period
- Fidelity: should mostly reflect transfers in plus a small amount of dividend/interest income

If anything looks wildly off, investigate before moving on. A wrong sign convention now will poison every downstream analysis.

## Definition of done

- [ ] All four remaining parsers implemented (Discover, Capital One, Fidelity)
- [ ] All five sources have fixture-based tests
- [ ] Capital One debit/credit column logic tested
- [ ] Fidelity excludes internal buy/sell from silver layer but preserves in bronze
- [ ] Cross-source sanity query results look right
- [ ] All tests pass

## Stop here

Show me the final cross-source query output and wait for verification before Phase 5.
