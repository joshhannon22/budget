# How to Prepare Sample Statements for Claude Code

This is for **you** (Josh), not for Claude Code. Read this and follow it before you kick off Phase 1. It tells you exactly how to export, sanitize, and place sample CSVs from each account so Claude Code can see the real data shape and write parsers that work on the first try.

## Why this matters

CSV formats vary across banks in ways prose can't fully describe — column orderings, date formats, quirky headers/footers, encoding, how credits and debits are represented. If Claude Code writes a parser without seeing a real sample, it will write something based on assumptions, and you'll spend hours fixing it. Five minutes of prep here saves a day of rework.

## What to export from each account

Aim for **1–3 months of recent transactions per account** — enough variety that Claude Code sees:

- Paychecks and direct deposits (PNC)
- Recurring bills (rent, utilities, streaming)
- Day-to-day spending (groceries, restaurants, coffee, transportation)
- Refunds or returns (negative purchases)
- Cashback / statement credits (credit cards)
- Internal transfers — at least one PNC → Fidelity and one PNC → credit card payment
- Pending vs posted transactions, if your bank exports both
- A foreign or unusual transaction if you have one
- For Fidelity: a contribution from PNC, a dividend or interest payment, a money market activity row

If your most recent 1–3 months don't naturally include all of these, expand the date range until they do.

### Per-account export instructions

| Account | Where to export |
|---|---|
| PNC | Online banking → Activity → Download → CSV. Choose a date range covering 2–3 months. |
| Fidelity | Activity & Orders → History → Download → CSV. **Choose the full transaction history export, not "positions."** |
| American Express | Statements & Activity → "Download CSV" → choose the **expanded** detail option (sometimes labeled "Activity" or "Custom"). The richer one includes Category, Address, Reference. Avoid the "summary" export. |
| Discover | Account → Activity → Download → CSV |
| Capital One | Account → View Transactions → Download → CSV. Capital One typically gives you separate Debit/Credit columns rather than a signed Amount column. |

## Sanitizing the samples

Open each CSV in a text editor (not Excel — Excel will silently mangle dates and leading zeros). Make these substitutions:

**Replace, but keep format intact:**
- Account numbers → `XXXX1234` (keep the same number of digits)
- Reference numbers → leave them; they're not sensitive
- Specific identifying merchants you'd rather not log (a therapist, an ex's Venmo, etc.) → swap for an equivalent generic (`THERAPY OFFICE`, `VENMO PAYMENT`)

**Do NOT change:**
- Column names — exact spelling, casing, and order
- Date formats — leave them in whatever format the bank exported
- Amount sign conventions — the parser needs to see the real sign behavior
- Header rows, blank rows, footer summary rows, BOM characters, encoding — all of this is what Claude Code needs to handle correctly
- Number of rows below 20 — give it variety; 20–60 rows per file is the sweet spot

**Optional:**
- You can shift dollar amounts by a small percentage if you want, but it's honestly more trouble than it's worth for personal data on a local-only project. Most people skip this.

## Where to put the files

After scaffolding the project (Phase 1), the directory `tests/fixtures/` will exist. Drop your sanitized files in with these exact names:

```
~/dev/budget/tests/fixtures/sample_pnc.csv
~/dev/budget/tests/fixtures/sample_fidelity.csv
~/dev/budget/tests/fixtures/sample_amex.csv
~/dev/budget/tests/fixtures/sample_discover.csv
~/dev/budget/tests/fixtures/sample_capital_one.csv
```

Filenames matter — the phase docs refer to them by these exact paths.

## When to deliver them to Claude Code

You don't need all five before you start. Sequence them with the phases:

1. **Before Phase 1:** none required (Phase 1 is pure scaffolding)
2. **Before Phase 2:** `sample_pnc.csv` must exist
3. **Before Phase 3:** `sample_amex.csv` must exist
4. **Before Phase 4:** `sample_discover.csv`, `sample_capital_one.csv`, `sample_fidelity.csv`

This staggers the work — you can start the project right now with just PNC ready, and prepare the others while Claude Code works on PNC.

## How Claude Code will use them

The phase docs explicitly tell Claude Code to read each fixture before writing the corresponding parser, document the format it observes in a comment at the top of the parser file, and use the fixture as the basis for parser tests. You don't need to paste the CSV contents into the chat — Claude Code has filesystem access in your VS Code project and will read them directly.

If a file is missing or looks wrong (e.g., Claude Code asks "I see only 3 rows, is this complete?"), it will pause and ask you. That's the right behavior — answer the question, fix the file, and resume.

## How to actually start the conversation with Claude Code

Once you've scaffolded a directory at `~/dev/budget` and dropped these markdown files into `docs/`, open VS Code in that directory and start Claude Code with something like:

> Read `CLAUDE.md` and `docs/phases/phase_01_scaffold.md`. Build out Phase 1 exactly as described. Stop when the definition-of-done checklist passes and summarize what you built.

Then verify Phase 1 yourself (run `budget init-db`, run the tests, look at the schema) before saying:

> Phase 1 looks good. Drop `sample_pnc.csv` into `tests/fixtures/`. Now read `docs/phases/phase_02_pnc_parser.md` and build it out.

Repeat for each phase. Doing it incrementally — and verifying between phases — is the whole point. It catches design problems early, when they're cheap to fix.

## Two pieces of advice

1. **Don't skip the verification step between phases.** It's tempting to let Claude Code run all seven phases unattended. Don't. Each phase is small enough to inspect in 10–15 minutes, and design issues compound fast if you don't catch them at the right phase boundary.

2. **The categorization rules in Phase 5 are seeds, not gospel.** The seeded patterns reflect generic merchants. After your first real run, you'll see a bunch of uncategorized rows that are specific to your life — your gym, your bodega, your Amazon prime habits. Plan to spend an hour or two after Phase 5 just adding rules until the uncategorized rate is under ~10%. That's where the system starts feeling like yours.
