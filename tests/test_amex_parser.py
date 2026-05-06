from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budgeting.parsers.amex import AmexParser

FIXTURE = Path(__file__).parent / "fixtures" / "sample_amex.csv"


@pytest.fixture(scope="module")
def transactions():
    parser = AmexParser()
    return list(parser.parse(FIXTURE))


def test_parse_without_error(transactions):
    assert len(transactions) > 0


def test_row_count(transactions):
    assert len(transactions) == 150


def test_all_amounts_are_decimal(transactions):
    for tx in transactions:
        assert isinstance(tx.amount, Decimal)


def test_all_dates_are_date_objects(transactions):
    for tx in transactions:
        assert isinstance(tx.transaction_date, date)
        assert tx.post_date is None


def test_purchase_is_negative_after_sign_flip(transactions):
    # Starbucks 10.00 in CSV → -10.00 stored (outflow)
    starbucks = [tx for tx in transactions if "STARBUCKS" in tx.description_raw and tx.transaction_date == date(2026, 5, 4)]
    assert len(starbucks) >= 1
    for tx in starbucks:
        assert tx.amount < 0, f"Purchase should be negative outflow, got {tx.amount}"


def test_payment_is_positive_after_sign_flip(transactions):
    # MOBILE PAYMENT -4000.00 in CSV → +4000.00 stored (inflow)
    payments = [tx for tx in transactions if "MOBILE PAYMENT" in tx.description_raw]
    assert len(payments) >= 1
    for tx in payments:
        assert tx.amount > 0, f"Payment should be positive inflow, got {tx.amount}"


def test_statement_credit_is_positive_after_sign_flip(transactions):
    # AMEX DUNKIN' CREDIT -7.00 in CSV → +7.00 stored
    # AMEX Dining Credit -10.00 in CSV → +10.00 stored
    credits = [tx for tx in transactions if "CREDIT" in tx.description_raw or "Credit" in tx.description_raw]
    assert len(credits) >= 1
    for tx in credits:
        assert tx.amount > 0, f"Statement credit should be positive inflow, got {tx.amount}"


def test_sign_flip_explicit():
    """Given a known CSV row with Amount=50.00, output amount must be -50.00."""
    import csv, io
    header = "Date,Description,Amount,Extended Details,Appears On Your Statement As,Address,City/State,Zip Code,Country,Reference,Category\n"
    row = "05/01/2026,TEST MERCHANT,50.00,details,TEST MERCHANT,123 Main St,\"NEW YORK\nNY\",10001,UNITED STATES,'REF123',Restaurant-Restaurant\n"
    parser = AmexParser()
    txs = list(parser.parse.__func__(parser, _csv_from_string(header + row)))
    assert txs[0].amount == Decimal("-50.00")


def test_category_source_populated(transactions):
    categorized = [tx for tx in transactions if tx.category_source is not None]
    assert len(categorized) > 0
    # Spot-check a known category
    groceries = [tx for tx in categorized if "Groceries" in (tx.category_source or "")]
    assert len(groceries) > 0


def test_payment_rows_have_no_category(transactions):
    payments = [tx for tx in transactions if "MOBILE PAYMENT" in tx.description_raw]
    for tx in payments:
        assert tx.category_source is None, f"Payment row should have no category, got {tx.category_source!r}"


def test_transaction_ids_are_unique(transactions):
    ids = [tx.transaction_id for tx in transactions]
    assert len(ids) == len(set(ids))


def test_transaction_ids_are_deterministic():
    parser = AmexParser()
    first_run = [tx.transaction_id for tx in parser.parse(FIXTURE)]
    second_run = [tx.transaction_id for tx in parser.parse(FIXTURE)]
    assert first_run == second_run


def test_account_fields(transactions):
    for tx in transactions:
        assert tx.account_source == "amex"
        assert tx.account_type == "credit_card"


def test_raw_payload_has_all_columns(transactions):
    expected_keys = {
        "Date", "Description", "Amount", "Extended Details",
        "Appears On Your Statement As", "Address", "City/State",
        "Zip Code", "Country", "Reference", "Category",
    }
    for tx in transactions:
        assert expected_keys <= set(tx.raw_payload.keys())


# Helper: create a temp Path from a string so we can test without a real file
import tempfile, os

def _csv_from_string(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)
