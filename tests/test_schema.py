import sqlite3
from pathlib import Path
import pytest

SCHEMA_PATH = Path(__file__).parents[1] / "src" / "budgeting" / "db" / "schema.sql"

EXPECTED_TABLES = {
    "raw_transactions",
    "transactions",
    "categorization_rules",
    "transfer_pairs",
    "ingestion_runs",
}

EXPECTED_INDEXES = {
    "idx_raw_source",
    "idx_raw_file",
    "idx_tx_date",
    "idx_tx_source",
    "idx_tx_category",
    "idx_tx_transfer",
    "idx_rules_priority",
}


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


def test_all_tables_exist(db):
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= table_names


def test_all_indexes_exist(db):
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    index_names = {row["name"] for row in rows}
    assert EXPECTED_INDEXES <= index_names


def test_foreign_key_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO transactions (
                transaction_id, raw_id, account_source, account_type,
                transaction_date, description_raw, amount
            ) VALUES ('abc123', 99999, 'pnc', 'checking', '2024-01-01', 'Test', -50.00)
            """
        )
        db.commit()


def test_raw_transactions_unique_constraint(db):
    db.execute(
        """
        INSERT INTO raw_transactions (account_source, source_file, row_number, raw_payload)
        VALUES ('pnc', 'test.csv', 1, '{}')
        """
    )
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO raw_transactions (account_source, source_file, row_number, raw_payload)
            VALUES ('pnc', 'test.csv', 1, '{}')
            """
        )
        db.commit()
