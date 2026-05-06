# Phase 6 — Internal Transfer Detection

**Prerequisites:** Phases 1–5 complete. Categorization working.

## Goal

Identify pairs of transactions that represent the same money moving between two accounts I own, and flag both legs as `is_transfer = true`. Without this, my "spending" totals double-count: a $1,000 PNC → Fidelity transfer would appear as -$1,000 outflow on PNC and +$1,000 inflow on Fidelity, inflating both spending and income figures.

The two main patterns:

1. **PNC → Fidelity** (saving/investing): -X on PNC, +X on Fidelity, within a few days
2. **PNC → credit card** (paying off Amex/Discover/Capital One): -X on PNC, +X on the card account, within a few days

## Step 1: Detection algorithm

In `src/budgeting/categorization/transfer_detection.py`:

```python
def detect_transfers(conn) -> list[tuple[str, str]]:
    """
    Find candidate transfer pairs.

    Pair criteria:
      - One transaction is an outflow (amount < 0), the other an inflow (amount > 0)
      - Absolute amounts equal (to the cent)
      - Different account_sources
      - Inflow date is within [outflow_date, outflow_date + 5 days]
        (banks take a few business days to settle)
      - Neither already paired
      - Both pass at least one heuristic that suggests transfer-ness:
          a) Description on either side contains transfer keywords:
             'TRANSFER', 'XFER', 'PAYMENT', 'AUTOPAY', 'ONLINE PYMT', 'WEB PMT',
             'FIDELITY', 'AMERICAN EXPRESS', 'AMEX', 'DISCOVER', 'CAPITAL ONE'
          b) The outflow source is PNC and the inflow source matches a known
             "destination" pattern (Fidelity, or any credit_card account)
    """
```

Two important details:

- **Match strict on amount, loose on date.** Same-amount false positives are rare; date-window false negatives (banks settle slowly) are common.
- **Require evidence** beyond just amount + date proximity. A coincidental $50 expense on Amex the same day as a $50 ATM withdrawal on PNC is not a transfer. The keyword/source heuristic prevents this.

When you find a pair:

1. Insert into `transfer_pairs(outflow_tx_id, inflow_tx_id, detection_method)`
2. Set `is_transfer = 1` on both transactions
3. Set both transactions' `category_unified = 'Transfers'`, `subcategory = 'Internal'`

## Step 2: Edge cases to handle explicitly

- **Partial credit card payments.** Sometimes you pay $500 toward a $1,200 Amex balance. The amounts will match exactly between the PNC outflow and Amex inflow even though it's not a "full" payment. That's fine — still a transfer.
- **Multiple transfers on the same day with the same amount.** Two $100 PNC → Fidelity transfers in one day. Match them in pair order (first outflow ↔ first matching inflow). Track which IDs are already paired so you don't double-pair.
- **Cashback / statement credits on credit cards.** These are inflows on the card but have **no** matching outflow anywhere — they're not transfers, they're income. Don't pair them. The keyword/source heuristic above already excludes them as long as the description doesn't contain transfer keywords.
- **Fidelity dividends and interest.** Same — inflows with no matching outflow on another account. Not transfers.
- **ATM withdrawals.** PNC outflow, no matching inflow anywhere (cash leaves the system). Not transfers.

## Step 3: CLI command

`budget detect-transfers [--dry-run]`:

- `--dry-run` prints the candidate pairs it would create without modifying the DB
- Default run inserts into `transfer_pairs` and updates `transactions`
- Idempotent: re-running doesn't create duplicate pairs (the `UNIQUE(outflow_tx_id, inflow_tx_id)` constraint guards this; handle the integrity error gracefully)

Print a summary: `"Detected 12 transfer pairs ($14,250 total). 3 candidates rejected for ambiguity."`

## Step 4: Run automatically after ingestion

Update `budget ingest` to run transfer detection after categorization. Order in the orchestrator:

1. Parse and load (bronze + silver)
2. Categorize
3. Detect transfers
4. Print summary

## Step 5: Manual override

Add a CLI escape hatch: `budget mark-transfer <outflow_id> <inflow_id>` for cases the heuristics miss. Useful when a description is unusual but you know it's a transfer.

Also add `budget unmark-transfer <pair_id>` to undo a false positive — sets `is_transfer = 0` on both legs and removes the row from `transfer_pairs`. Re-categorize the affected rows after unmarking.

## Step 6: Tests

`tests/test_transfer_detection.py`:

- A clean PNC→Fidelity transfer is detected
- A clean PNC→Amex payment is detected
- Coincidental same-amount transactions without evidence are **not** paired
- Cashback inflow on Amex is not paired with anything
- Two $100 PNC→Fidelity transfers on the same day produce two pairs, not one or four
- A transfer with a 4-day settlement gap is detected
- A transfer with a 7-day gap is **not** detected (outside window)
- Re-running detection is idempotent

## Step 7: Sanity check

After running detection on all fixture data:

```sql
-- Spending totals excluding transfers (this is the number that actually matters)
SELECT category_unified,
       SUM(amount) as net_amount,
       COUNT(*) as n
FROM transactions
WHERE is_transfer = 0
  AND amount < 0
GROUP BY category_unified
ORDER BY net_amount;

-- Verify transfer pairs net to zero
SELECT pair_id,
       outflow_tx_id, inflow_tx_id,
       (SELECT amount FROM transactions WHERE transaction_id = outflow_tx_id) as outflow_amt,
       (SELECT amount FROM transactions WHERE transaction_id = inflow_tx_id) as inflow_amt
FROM transfer_pairs;
```

Every row in the second query should show `outflow_amt + inflow_amt = 0`. If any don't, the matching logic has a bug.

## Definition of done

- [ ] `detect_transfers()` implemented with documented heuristics
- [ ] Edge cases (cashback, ATM, partial payments, same-day duplicates) handled
- [ ] CLI commands work, including dry-run and manual overrides
- [ ] Detection runs automatically after ingestion
- [ ] Transfer pairs always net to zero (verified by query)
- [ ] Tests pass

## Stop here

Show me the spending-by-category query results (with transfers excluded). This should be the first time the data tells a true story about where my money goes. Wait for verification before Phase 7.
