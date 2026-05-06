from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budgeting.parsers.pnc import PNCParser

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pnc.csv"


@pytest.fixture(scope="module")
def transactions():
    parser = PNCParser()
    return list(parser.parse(FIXTURE))


def test_parse_without_error(transactions):
    assert len(transactions) > 0


def test_row_count(transactions):
    assert len(transactions) == 51


def test_all_amounts_are_decimal(transactions):
    for tx in transactions:
        assert isinstance(tx.amount, Decimal), f"Expected Decimal, got {type(tx.amount)}"


def test_all_dates_are_date_objects(transactions):
    for tx in transactions:
        assert isinstance(tx.transaction_date, date)
        assert tx.post_date is None  # PNC has no post date column


def test_paycheck_row(transactions):
    # "MIZUHO AMERICAS PAYROLL ACH CREDIT xxxxxxxxxxx7472","+ $3778.79","Paychecks"
    paychecks = [tx for tx in transactions if "MIZUHO AMERICAS PAYROLL" in tx.description_raw]
    assert len(paychecks) >= 1
    for tx in paychecks:
        assert tx.amount > 0, "Paycheck should be positive (inflow)"
        assert tx.account_source == "pnc"
        assert tx.account_type == "checking"
        assert tx.category_source == "Paychecks"


def test_expense_row(transactions):
    # "FIRSTMARK PAYMENTS ACH WEB-RECUR xxx0565","- $224.26","Loans"
    loans = [tx for tx in transactions if "FIRSTMARK" in tx.description_raw]
    assert len(loans) >= 1
    for tx in loans:
        assert tx.amount < 0, "Loan payment should be negative (outflow)"
        assert tx.category_source == "Loans"


def test_transfer_out_row(transactions):
    # "AMEX EPAYMENT ACH PMT ACH WEB M0076","- $4000","Credit Card Payments"
    amex_payments = [tx for tx in transactions if "AMEX EPAYMENT" in tx.description_raw]
    assert len(amex_payments) >= 1
    for tx in amex_payments:
        assert tx.amount < 0, "Credit card payment should be negative (outflow)"
        assert tx.category_source == "Credit Card Payments"


def test_transaction_ids_are_unique(transactions):
    ids = [tx.transaction_id for tx in transactions]
    assert len(ids) == len(set(ids)), "Duplicate transaction_ids detected"


def test_transaction_ids_are_deterministic():
    parser = PNCParser()
    first_run = [tx.transaction_id for tx in parser.parse(FIXTURE)]
    second_run = [tx.transaction_id for tx in parser.parse(FIXTURE)]
    assert first_run == second_run


def test_account_fields(transactions):
    for tx in transactions:
        assert tx.account_source == "pnc"
        assert tx.account_type == "checking"


def test_row_numbers_sequential(transactions):
    row_numbers = [tx.row_number for tx in transactions]
    assert row_numbers == list(range(1, len(transactions) + 1))


def test_raw_payload_preserved(transactions):
    for tx in transactions:
        assert isinstance(tx.raw_payload, dict)
        assert "Transaction Date" in tx.raw_payload
        assert "Transaction Description" in tx.raw_payload
        assert "Amount" in tx.raw_payload
