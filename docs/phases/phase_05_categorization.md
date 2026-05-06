# Phase 5 — Unified Categorization Rules Engine

**Prerequisites:** Phases 1–4 complete. All five sources ingesting cleanly into bronze and silver.

## Goal

Apply consistent categorization across every source. Each bank uses different category names — Amex says "Restaurants", Discover says "Restaurants", Capital One says "Dining", PNC may not provide a category at all. After this phase, every transaction has a `category_unified` value drawn from a single taxonomy that I control.

Categorization is a **layered cascade**, evaluated in priority order:

1. **Merchant pattern rules** (highest priority) — regex patterns matched against `description_raw`. Highest-fidelity, deterministic.
2. **Source category mapping** — bank's native category mapped to my unified taxonomy. Catches whatever the merchant rules miss.
3. **Uncategorized** — anything that falls through. Reviewed periodically; new rules added.

No LLM. No fuzzy matching. Pure deterministic rules I can read and reason about.

## Step 1: Define the unified taxonomy

Create `src/budgeting/categorization/taxonomy.py`:

```python
# Unified category taxonomy. Two-level: category + subcategory.
TAXONOMY = {
    "Food": ["Groceries", "Restaurants", "Coffee", "Delivery", "Bars"],
    "Transportation": ["Rideshare", "Transit", "Gas", "Parking", "Tolls", "Air Travel"],
    "Housing": ["Rent", "Utilities", "Internet", "Phone", "Maintenance", "Furnishings"],
    "Shopping": ["Clothing", "Electronics", "Home Goods", "Personal Care", "General"],
    "Entertainment": ["Streaming", "Concerts", "Games", "Events", "Books & Media"],
    "Health": ["Medical", "Pharmacy", "Fitness", "Insurance"],
    "Travel": ["Lodging", "Air Travel", "Car Rental", "Other Travel"],
    "Income": ["Salary", "Interest", "Dividends", "Cashback", "Refund", "Other Income"],
    "Investments": ["Contribution", "Dividend Reinvest"],
    "Transfers": ["Internal"],
    "Fees": ["Bank Fees", "Card Fees", "Late Fees", "Other Fees"],
    "Uncategorized": ["Uncategorized"],
}
```

Validate at import time that every (category, subcategory) used in rules exists here.

## Step 2: Create the rules file

`src/budgeting/categorization/rules.yaml` — start with high-confidence patterns. Examples to seed it with:

```yaml
# Format: list of rules in priority order (lower priority number = evaluated first)
- priority: 100
  pattern: "(?i)BLUE BOTTLE|STARBUCKS|DUNKIN|PHILZ"
  category: Food
  subcategory: Coffee
  merchant_clean: ""  # leave empty for now, populated by gold layer if desired

- priority: 110
  pattern: "(?i)WHOLE FOODS|TRADER JOE|H-MART|WEGMANS|GIANT|SAFEWAY|FAIRWAY"
  category: Food
  subcategory: Groceries

- priority: 120
  pattern: "(?i)UBER\\s*EATS|DOORDASH|GRUBHUB|SEAMLESS|CAVIAR"
  category: Food
  subcategory: Delivery

- priority: 130
  pattern: "(?i)UBER(?!\\s*EATS)|LYFT"
  category: Transportation
  subcategory: Rideshare

- priority: 140
  pattern: "(?i)MTA|METROCARD|NJ TRANSIT|PATH|AMTRAK"
  category: Transportation
  subcategory: Transit

- priority: 150
  pattern: "(?i)SHELL|EXXON|BP|MOBIL|CHEVRON|SUNOCO"
  category: Transportation
  subcategory: Gas

- priority: 200
  pattern: "(?i)NETFLIX|SPOTIFY|HULU|DISNEY\\+|MAX|HBO|APPLE\\.COM/BILL|YOUTUBE PREMIUM"
  category: Entertainment
  subcategory: Streaming

- priority: 210
  pattern: "(?i)CONED|CONSOLIDATED EDISON|NATIONAL GRID|PSEG"
  category: Housing
  subcategory: Utilities

- priority: 220
  pattern: "(?i)VERIZON|SPECTRUM|XFINITY|OPTIMUM|T-MOBILE|AT&T"
  category: Housing
  subcategory: Internet  # or Phone — refine over time

# Income patterns (positive amounts on PNC)
- priority: 300
  pattern: "(?i)MIZUHO.*PAYROLL|DIRECT DEP.*MIZUHO|ADP.*PAYROLL"
  category: Income
  subcategory: Salary

# Bank fees
- priority: 400
  pattern: "(?i)OVERDRAFT|MONTHLY SERVICE FEE|MAINTENANCE FEE"
  category: Fees
  subcategory: Bank Fees

# Catch-all transfer indicators (final pass at credit card payments — Phase 6 will refine)
- priority: 900
  pattern: "(?i)PAYMENT\\s*-\\s*THANK YOU|AUTOPAY|ONLINE PAYMENT"
  category: Transfers
  subcategory: Internal
```

These are seeds — you'll grow this file over time as you review uncategorized transactions. Tune the patterns based on what actually appears in your fixtures.

## Step 3: Build the rules engine

`src/budgeting/categorization/rules.py`:

- Load `rules.yaml` once at startup; validate every (category, subcategory) pair against `TAXONOMY`
- Compile each pattern with `re.compile(...)` upfront — don't recompile per row
- Optionally load rules into the `categorization_rules` table for visibility, but the YAML is the source of truth (treat the table as a cache/audit trail, not a primary store)
- Provide `categorize(description: str, source_category: str | None, account_source: str) -> tuple[str, str]` that returns `(category_unified, subcategory)`:
  1. Walk rules in priority order; return on first match where the rule's `account_source` is `None` or matches the transaction
  2. If no rule matched, fall back to source-category mapping (Step 4)
  3. If still no match, return `("Uncategorized", "Uncategorized")`

## Step 4: Source category mapping

`src/budgeting/categorization/source_mapping.yaml`:

A second YAML file mapping each bank's native categories to your unified taxonomy. Example:

```yaml
amex:
  "Restaurants": [Food, Restaurants]
  "Merchandise & Supplies-Groceries": [Food, Groceries]
  "Travel-Airlines": [Travel, Air Travel]
  "Travel-Lodging": [Travel, Lodging]
  "Transportation-Taxi": [Transportation, Rideshare]
  "Other-Miscellaneous": [Uncategorized, Uncategorized]

discover:
  "Restaurants": [Food, Restaurants]
  "Supermarkets": [Food, Groceries]
  "Gasoline": [Transportation, Gas]
  "Travel/ Entertainment": [Entertainment, Events]

capital_one:
  "Dining": [Food, Restaurants]
  "Grocery": [Food, Groceries]
  "Gas/Automotive": [Transportation, Gas]
  "Other": [Uncategorized, Uncategorized]
```

You'll populate this against the actual category strings in your real exports — start with what you observe in the fixtures. PNC and Fidelity may have nothing to map.

## Step 5: Apply categorization

Add a CLI command: `budget categorize [--all | --uncategorized-only]`

- Iterates `transactions` rows
- For each, calls `categorize(...)` and updates `category_unified` and `subcategory`
- `--uncategorized-only` only updates rows where `category_unified IS NULL` or `= 'Uncategorized'`
- `--all` re-categorizes every row (useful when you've added new rules)

Run this automatically at the end of `budget ingest` so newly ingested rows are categorized immediately.

## Step 6: Review tooling

Add `budget review-uncategorized` that prints the top 20 most frequent uncategorized merchants (descriptions grouped by a normalized form — strip dates, store numbers, location codes) with counts and total amount. This is your feedback loop for adding new rules.

A useful normalization for the grouping: lowercase, strip digits, strip common location tokens (`#1234`, ` NYC`, ` NY`), collapse whitespace.

## Step 7: Tests

`tests/test_categorization.py`:

- Unknown taxonomy entries in `rules.yaml` raise at load time
- Priority order is respected — a more specific high-priority rule wins over a more generic low-priority rule
- Account-scoped rules only match their account
- Source mapping fallback works when no merchant rule matches
- Uncategorized fallback works when nothing matches
- Specific cases from your fixtures: at least 5 real transactions you'd expect to categorize, asserted

## Definition of done

- [ ] Taxonomy defined and validated
- [ ] `rules.yaml` and `source_mapping.yaml` both exist with seed entries
- [ ] Rules engine loads, validates, and categorizes correctly
- [ ] `budget ingest` runs categorization automatically
- [ ] `budget categorize` and `budget review-uncategorized` commands work
- [ ] Tests pass
- [ ] After running on all five fixtures, the uncategorized rate is below 30% — if it's higher, add rules until it isn't

## Stop here

Show me the output of `budget review-uncategorized` and the percentage of rows still uncategorized. Wait for verification before Phase 6.
