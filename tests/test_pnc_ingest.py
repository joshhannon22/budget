from pathlib import Path

import pytest

from budgeting.db.connection import get_connection
from budgeting.ingest import run_ingest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pnc.csv"
SCHEMA = Path(__file__).parents[1] / "src" / "budgeting" / "db" / "schema.sql"


@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / "test.db"
    conn = get_connection(db)
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def archive_root(tmp_path):
    return tmp_path / "archive"


def test_ingest_row_counts(db_path, archive_root):
    result = run_ingest(FIXTURE, "pnc", db_path=db_path, archive_root=archive_root)

    assert result["rows_read"] == 51
    assert result["rows_inserted"] == 51
    assert result["rows_skipped"] == 0

    conn = get_connection(db_path)
    raw_count = conn.execute("SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
    tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()

    assert raw_count == 51
    assert tx_count == 51


def test_ingest_is_idempotent(db_path, archive_root):
    first = run_ingest(FIXTURE, "pnc", db_path=db_path, archive_root=archive_root)
    assert first["rows_inserted"] == 51

    second = run_ingest(FIXTURE, "pnc", db_path=db_path, archive_root=archive_root)
    assert second["rows_read"] == 51
    assert second["rows_inserted"] == 0
    assert second["rows_skipped"] == 51

    conn = get_connection(db_path)
    tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    assert tx_count == 51


def test_ingestion_run_logged(db_path, archive_root):
    run_ingest(FIXTURE, "pnc", db_path=db_path, archive_root=archive_root)

    conn = get_connection(db_path)
    run = conn.execute(
        "SELECT * FROM ingestion_runs WHERE account_source='pnc'"
    ).fetchone()
    conn.close()

    assert run is not None
    assert run["status"] == "success"
    assert run["rows_read"] == 51
    assert run["rows_inserted"] == 51
    assert run["rows_skipped"] == 0
    assert run["completed_at"] is not None


def test_csv_archived(archive_root, db_path):
    run_ingest(FIXTURE, "pnc", db_path=db_path, archive_root=archive_root)
    archived_files = list((archive_root).glob("pnc_*.csv"))
    assert len(archived_files) == 1
    assert archived_files[0].stat().st_size > 0


def test_transactions_have_correct_source(db_path, archive_root):
    run_ingest(FIXTURE, "pnc", db_path=db_path, archive_root=archive_root)

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT DISTINCT account_source, account_type FROM transactions"
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["account_source"] == "pnc"
    assert rows[0]["account_type"] == "checking"
