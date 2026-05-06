# Phase 3 — American Express Parser

**Prerequisites:** Phase 2 complete. PNC ingestion working and idempotent.

## Goal

Add the Amex parser. Amex is your highest-volume source and provides the richest category data, so this parser will surface most of the categorization edge cases you'll need to handle in Phase 5.

## Step 1: Verify the right export

Amex offers multiple CSV export options. Make sure `tests/fixtures/sample_amex.csv` came from the **richer** export — the one with extended transaction details (category, address, reference number) — not the summary version. If unsure, ask me before proceeding.

## Step 2: Read the fixture

Same drill as Phase 2. Read `tests/fixtures/sample_amex.csv` and document at the top of `src/budgeting/parsers/amex.py`:

- Column names and order
- Date format
- Amount sign convention — Amex typically reports purchases as positive numbers and credits/payments as negative, which is the **opposite** of our internal convention. Flip the sign on ingest.
- How are statement credits, cashback rewards, and payments to the card represented?
- Category column — what does Amex's native taxonomy look like? (e.g., "Restaurants", "Travel-Airlines", "Merchandise & Supplies-Internet Purchase")
- Any extended-detail columns (Address, City/State, Zip, Country, Reference, Description) worth preserving in `raw_payload`

## Step 3: Implement `AmexParser`

In `src/budgeting/parsers/amex.py`:

- Subclass `BaseParser`
- `account_source = "amex"`, `account_type = "credit_card"`
- **Sign flip:** Amex purchases come in as positive; we store them as negative (outflow). Payments and credits come in as negative; we store them as positive (inflow). Document this explicitly in a comment.
- Capture Amex's category in `category_source` verbatim — Phase 5 will map these to your unified taxonomy
- Same idempotency rules as PNC: deterministic `transaction_id` with occurrence counter
- Preserve the extended details in `raw_payload` even if not yet used downstream

## Step 4: Register and ingest

- Add `AmexParser` to the parser registry in the CLI
- Run `budget ingest tests/fixtures/sample_amex.csv --source amex`
- Verify rows land in both `raw_transactions` and `transactions` with correct signs

## Step 5: Cross-source sanity check

Run this query after ingesting both PNC and Amex fixtures:

```sql
SELECT account_source, account_type,
       COUNT(*) as n,
       SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) as outflows,
       SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as inflows,
       MIN(transaction_date) as earliest,
       MAX(transaction_date) as latest
FROM transactions
GROUP BY account_source, account_type;
```

Eyeball the result:

- Does the outflow/inflow split match what you'd expect? Amex should be mostly outflows with a handful of inflows (payments, credits). PNC depends on the period.
- Do the date ranges match what you exported?

## Step 6: Tests

`tests/test_amex_parser.py`:

- Parses fixture without error, yields expected row count
- Spot-check: a purchase (negative after flip), a payment (positive after flip), a statement credit / cashback (positive)
- Sign flip is explicitly tested — given a known input row of `+50.00`, output is `-50.00`
- `category_source` is populated from the Amex category column

## Definition of done

- [ ] Fixture format documented in parser header comment
- [ ] Sign flip implemented and tested
- [ ] `category_source` populated
- [ ] Ingestion idempotent
- [ ] Both PNC and Amex visible in the cross-source query
- [ ] All tests pass

## Stop here

Show me the cross-source query output and wait for verification before Phase 4.
