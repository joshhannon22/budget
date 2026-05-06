# American Express CSV format (observed from sample fixture):
#
# Columns (exactly 11):
#   Date                    — MM/DD/YYYY
#   Description             — short merchant name (sometimes truncated)
#   Amount                  — plain decimal, NO currency symbol or sign prefix
#   Extended Details        — multi-line field with full merchant details, phone,
#                             reference codes; embedded newlines handled by csv.DictReader
#   Appears On Your Statement As — statement description (may differ from Description)
#   Address                 — street address
#   City/State              — multi-line "CITY\nST" embedded newline
#   Zip Code                — postal code
#   Country                 — e.g. "UNITED STATES"
#   Reference               — Amex's own transaction reference, e.g. '320261240511742021'
#   Category                — Amex's own taxonomy e.g. "Restaurant-Bar & Café",
#                             "Merchandise & Supplies-Internet Purchase",
#                             "Transportation-Rail Services"; EMPTY for payment rows
#
# No separate post date column.
# Encoding: UTF-8.
#
# SIGN CONVENTION — CRITICAL:
#   Amex exports purchases as POSITIVE numbers and credits/payments as NEGATIVE.
#   This is the opposite of our internal convention (negative=outflow, positive=inflow).
#   We negate every amount on ingest:
#     Purchase  +10.00  →  -10.00  (outflow)
#     Payment  -4000.00 →  +4000.00 (inflow)
#     Credit     -7.00  →   +7.00  (inflow)

import csv
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from budgeting.models import NormalizedTransaction
from budgeting.parsers.base import BaseParser

_EXPECTED_COLUMNS = {
    "Date",
    "Description",
    "Amount",
    "Extended Details",
    "Appears On Your Statement As",
    "Address",
    "City/State",
    "Zip Code",
    "Country",
    "Reference",
    "Category",
}


class AmexParser(BaseParser):
    account_source = "amex"
    account_type = "credit_card"

    def parse(self, csv_path: Path) -> Iterator[NormalizedTransaction]:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)

            actual = set(reader.fieldnames or [])
            unrecognized = actual - _EXPECTED_COLUMNS
            missing = _EXPECTED_COLUMNS - actual
            if unrecognized:
                raise ValueError(f"Amex CSV has unrecognized columns: {unrecognized}")
            if missing:
                raise ValueError(f"Amex CSV is missing expected columns: {missing}")

            occurrence_counter: Counter = Counter()

            for row_number, row in enumerate(reader, start=1):
                date_str = row["Date"].strip()
                description = row["Description"].strip()
                amount_raw = row["Amount"].strip()
                category_raw = row["Category"].strip()

                try:
                    transaction_date = datetime.strptime(date_str, "%m/%d/%Y").date()
                except ValueError:
                    raise ValueError(
                        f"Amex row {row_number}: unparseable date {date_str!r}"
                    )

                try:
                    # Negate: Amex positive = our outflow (negative), and vice versa
                    amount = -Decimal(amount_raw.replace(",", ""))
                except InvalidOperation:
                    raise ValueError(
                        f"Amex row {row_number}: unparseable amount {amount_raw!r}"
                    )

                category_source = category_raw or None

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
                    category_source=category_source,
                    is_pending=False,
                    raw_payload=dict(row),
                    source_file=str(csv_path),
                    row_number=row_number,
                )
