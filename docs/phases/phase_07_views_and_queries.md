# Phase 7 — Analytical Views and Common Queries

**Prerequisites:** Phases 1–6 complete. Data is ingested, categorized, and transfers flagged.

## Goal

Make the data easy to query for the questions I'll actually ask. Build a set of SQL views and a small CLI report layer. This is the foundation for whatever visualization layer comes later — when the dashboard project starts, it'll just call these views.

No dashboards in this phase. Just clean, well-named views and a few CLI commands that print useful summaries.

## Step 1: Core views

Add these to `src/budgeting/db/migrations/002_views.sql` (and run them as part of `init-db` going forward):

### `v_spending` — every outflow that isn't a transfer

```sql
CREATE VIEW IF NOT EXISTS v_spending AS
SELECT
    transaction_id,
    account_source,
    account_type,
    transaction_date,
    description_raw,
    merchant_clean,
    ABS(amount) as amount,           -- positive in this view for easier aggregation
    category_unified,
    subcategory
FROM transactions
WHERE is_transfer = 0
  AND amount < 0;
```

Convention: in `transactions`, expenses are negative. In `v_spending`, they're positive — much easier to read in reports and chart.

### `v_income` — every inflow that isn't a transfer

```sql
CREATE VIEW IF NOT EXISTS v_income AS
SELECT
    transaction_id,
    account_source,
    transaction_date,
    description_raw,
    amount,
    category_unified,
    subcategory
FROM transactions
WHERE is_transfer = 0
  AND amount > 0;
```

### `v_monthly_spending_by_category`

```sql
CREATE VIEW IF NOT EXISTS v_monthly_spending_by_category AS
SELECT
    strftime('%Y-%m', transaction_date) as month,
    category_unified,
    subcategory,
    SUM(amount) as total,
    COUNT(*) as n_transactions,
    ROUND(AVG(amount), 2) as avg_transaction
FROM v_spending
GROUP BY month, category_unified, subcategory
ORDER BY month DESC, total DESC;
```

### `v_top_merchants`

```sql
CREATE VIEW IF NOT EXISTS v_top_merchants AS
SELECT
    COALESCE(merchant_clean, description_raw) as merchant,
    category_unified,
    SUM(amount) as total,
    COUNT(*) as n_transactions,
    MIN(transaction_date) as first_seen,
    MAX(transaction_date) as last_seen
FROM v_spending
GROUP BY merchant, category_unified
ORDER BY total DESC;
```

### `v_recurring_candidates` — heuristic for subscriptions and bills

A transaction is a "recurring candidate" if the same merchant appears in 3+ different months with similar amounts (within 5%).

```sql
CREATE VIEW IF NOT EXISTS v_recurring_candidates AS
WITH merchant_months AS (
    SELECT
        COALESCE(merchant_clean, description_raw) as merchant,
        category_unified,
        strftime('%Y-%m', transaction_date) as month,
        SUM(amount) as monthly_total,
        COUNT(*) as n_per_month
    FROM v_spending
    GROUP BY merchant, category_unified, month
)
SELECT
    merchant,
    category_unified,
    COUNT(DISTINCT month) as n_months,
    ROUND(AVG(monthly_total), 2) as avg_monthly,
    ROUND(MIN(monthly_total), 2) as min_monthly,
    ROUND(MAX(monthly_total), 2) as max_monthly
FROM merchant_months
GROUP BY merchant, category_unified
HAVING n_months >= 3
   AND (MAX(monthly_total) - MIN(monthly_total)) / AVG(monthly_total) < 0.05
ORDER BY avg_monthly DESC;
```

### `v_account_balances_flow` — net cash flow per account per month

```sql
CREATE VIEW IF NOT EXISTS v_account_balances_flow AS
SELECT
    account_source,
    account_type,
    strftime('%Y-%m', transaction_date) as month,
    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as inflows,
    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as outflows,
    SUM(amount) as net
FROM transactions
GROUP BY account_source, account_type, month
ORDER BY month DESC, account_source;
```

## Step 2: CLI reports

Add these commands to the CLI. Use the `rich` library for nice terminal tables.

### `budget report monthly [--month YYYY-MM]`

Defaults to most recent complete month. Shows:

- Total spending, total income, net
- Spending by category with subcategory breakdown
- Top 10 merchants
- Comparison to previous month (% change per category)

### `budget report recurring`

Lists all rows from `v_recurring_candidates` with avg monthly, min, max. This is what becomes "your subscriptions and recurring bills" in any future dashboard.

### `budget report category <category> [--months N]`

Drill into a single category over the last N months (default 6). Shows trend per subcategory and lists every transaction.

### `budget report uncategorized`

Same as `budget review-uncategorized` from Phase 5, but lifted into the report namespace for consistency. Keep the old command as an alias.

## Step 3: Export for downstream tools

Add `budget export <output_path> [--format csv|parquet] [--view <view_name>]`:

- Default exports `transactions` table
- `--view v_spending` exports a specific view
- Parquet support optional but nice; falls back gracefully if `pyarrow` isn't installed

This is the seam where the future visualization layer plugs in. A dashboard project can either query the SQLite directly or consume parquet exports — both options stay open.

## Step 4: Tests

`tests/test_views.py`:

- Each view exists after migration
- `v_spending` excludes all `is_transfer = 1` rows and all positive-amount rows
- `v_income` excludes transfers and negative-amount rows
- `v_monthly_spending_by_category` totals match the underlying data
- `v_recurring_candidates` correctly flags a fabricated 3-month $15.99 Spotify pattern
- `budget report monthly` runs without error against the fixture data and produces non-empty output

## Step 5: Documentation

Update `README.md` with a "Common queries" section showing the views and a couple of example direct-SQL queries for ad-hoc analysis. This is the manual I'll consult when I want to ask a one-off question.

Suggested examples:

```sql
-- How much did I spend on coffee this year?
SELECT strftime('%Y-%m', transaction_date) as month, SUM(amount) as total
FROM v_spending
WHERE category_unified = 'Food' AND subcategory = 'Coffee'
  AND transaction_date >= date('now', '-12 months')
GROUP BY month;

-- Where did my Amex spend go last month?
SELECT category_unified, subcategory, SUM(amount) as total
FROM v_spending
WHERE account_source = 'amex'
  AND strftime('%Y-%m', transaction_date) = strftime('%Y-%m', date('now', '-1 month'))
GROUP BY category_unified, subcategory
ORDER BY total DESC;

-- Net savings per month (income - spending, ignoring transfers)
SELECT strftime('%Y-%m', transaction_date) as month,
       SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
       SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) as spending,
       SUM(amount) as net
FROM transactions
WHERE is_transfer = 0
GROUP BY month
ORDER BY month DESC;
```

## Definition of done

- [ ] All views created via migration
- [ ] `budget report monthly`, `report recurring`, `report category`, `report uncategorized` all work
- [ ] `budget export` produces valid CSV (and parquet if pyarrow installed)
- [ ] Tests pass
- [ ] README updated with example queries
- [ ] After running `budget report monthly` on real data, the output passes the gut-check: do the totals match what I remember spending?

## Where this leaves us

After Phase 7, the pipeline is feature-complete for ingestion, normalization, categorization, and analysis. What's next is up to me:

- **Visualization layer** — Streamlit, Dash, or a static dashboard project that reads from SQLite/parquet
- **Budget tracking** — a `budgets` table with monthly targets per category, plus reports comparing actual vs budget
- **LLM-assisted categorization** — for the long-tail uncategorized rows
- **Bank API integration** — replace CSV exports with Plaid (only if I want to)

None of those are part of this project. The data foundation is the work, and once it's solid, everything else is straightforward to layer on.

## Stop here

Show me `budget report monthly` output for the most recent complete month in the fixture data. That's the deliverable.
