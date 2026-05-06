# PNC Checking CSV format (observed from sample fixture):
#
# Columns (exactly 5, no extras):
#   Transaction Date    — ISO format: YYYY-MM-DD, single date column (no separate post date)
#   Transaction Description — free-text; includes merchant, ACH details, check numbers
#   Amount              — string prefixed with "+ $" (inflow) or "- $" (outflow)
#                         e.g. "+ $3778.79", "- $137.98", "- $4000"
#                         no thousands commas seen, but stripped defensively
#   Category            — PNC's own taxonomy (e.g. "Paychecks", "Credit Card Payments",
#                         "Transfers", "Cash Withdrawals", "Services and Supplies", etc.)
#   Balance             — running balance string, e.g. "$8584.75" — ignored
#
# No header junk, no footer rows, no blank rows.
# All rows are quoted. Encoding is UTF-8.
# Sign convention applied here:
#   "- $..." → negative Decimal (outflow)
#   "+ $..." → positive Decimal (inflow)

import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from budgeting.models import NormalizedTransaction
from budgeting.parsers.base import BaseParser

_EXPECTED_COLUMNS = {
    "Transaction Date",
    "Transaction Description",
    "Amount",
    "Category",
    "Balance",
}


def _parse_amount(raw: str) -> Decimal:
    raw = raw.strip()
    if raw.startswith("+ $"):
        return Decimal(raw[3:].replace(",", ""))
    elif raw.startswith("- $"):
        return -Decimal(raw[3:].replace(",", ""))
    raise ValueError(f"Unrecognized PNC amount format: {raw!r}")


class PNCParser(BaseParser):
    account_source = "pnc"
    account_type = "checking"

    def parse(self, csv_path: Path) -> Iterator[NormalizedTransaction]:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)

            actual = set(reader.fieldnames or [])
            unrecognized = actual - _EXPECTED_COLUMNS
            missing = _EXPECTED_COLUMNS - actual
            if unrecognized:
                raise ValueError(f"PNC CSV has unrecognized columns: {unrecognized}")
            if missing:
                raise ValueError(f"PNC CSV is missing expected columns: {missing}")

            # Track (date, amount_str, description) tuples to generate stable
            # occurrence_index values for same-day duplicates.
            occurrence_counter: Counter = Counter()

            for row_number, row in enumerate(reader, start=1):
                date_str = row["Transaction Date"].strip()
                description = row["Transaction Description"].strip()
                amount_raw = row["Amount"].strip()
                category = row["Category"].strip() or None

                try:
                    from datetime import date
                    transaction_date = date.fromisoformat(date_str)
                except ValueError:
                    raise ValueError(
                        f"PNC row {row_number}: unparseable date {date_str!r}"
                    )

                try:
                    amount = _parse_amount(amount_raw)
                except (ValueError, InvalidOperation) as exc:
                    raise ValueError(
                        f"PNC row {row_number}: unparseable amount {amount_raw!r}"
                    ) from exc

                dedup_key = (date_str, amount_raw, description)
                occurrence_index = occurrence_counter[dedup_key]
                occurrence_counter[dedup_key] += 1

                transaction_id = self.make_transaction_id(
                    account_source=self.account_source,
                    transaction_date=date_str,
                    amount=amount_raw,
                    description=description,
                    occurrence_index=occurrence_index,
                )

                yield NormalizedTransaction(
                    transaction_id=transaction_id,
                    account_source=self.account_source,
                    account_type=self.account_type,
                    transaction_date=transaction_date,
                    post_date=None,
                    description_raw=description,
                    amount=amount,
                    category_source=category,
                    is_pending=False,
                    raw_payload=dict(row),
                    source_file=str(csv_path),
                    row_number=row_number,
                )
