import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from budgeting.db.connection import DB_PATH, get_connection

PROJECT_ROOT = Path(__file__).parents[2]


def _get_parser(source: str):
    from budgeting.parsers.amex import AmexParser
    from budgeting.parsers.pnc import PNCParser

    registry = {
        "pnc": PNCParser,
        "fidelity": None,
        "amex": AmexParser,
        "discover": None,
        "capital_one": None,
    }
    if source not in registry:
        raise ValueError(
            f"Unknown source: {source!r}. Known sources: {list(registry)}"
        )
    cls = registry[source]
    if cls is None:
        raise NotImplementedError(f"Parser for {source!r} not yet implemented")
    return cls()


def _archive_csv(csv_path: Path, source: str, archive_root: Path | None = None) -> Path:
    if archive_root is None:
        archive_root = PROJECT_ROOT / "data" / "raw" / source
    archive_root.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    dest = archive_root / f"{source}_{today}_{csv_path.name}"
    if not dest.exists():
        shutil.copy2(csv_path, dest)
    return dest


def run_ingest(
    csv_path: Path,
    source: str,
    db_path: Path = DB_PATH,
    archive_root: Path | None = None,
) -> dict:
    parser = _get_parser(source)
    archived = _archive_csv(csv_path, source, archive_root)

    try:
        source_file = str(archived.relative_to(PROJECT_ROOT))
    except ValueError:
        source_file = str(archived)

    conn = get_connection(db_path)
    started_at = datetime.now().isoformat()
    rows_read = rows_inserted = rows_skipped = 0
    run_id = None

    try:
        cur = conn.execute(
            """
            INSERT INTO ingestion_runs
                (account_source, source_file, rows_read, rows_inserted,
                 rows_skipped, started_at, status)
            VALUES (?, ?, 0, 0, 0, ?, 'started')
            """,
            (source, source_file, started_at),
        )
        run_id = cur.lastrowid

        for tx in parser.parse(archived):
            rows_read += 1

            try:
                conn.execute(
                    """
                    INSERT INTO raw_transactions
                        (account_source, source_file, row_number, raw_payload)
                    VALUES (?, ?, ?, ?)
                    """,
                    (source, source_file, tx.row_number, json.dumps(tx.raw_payload)),
                )
                raw_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            except sqlite3.IntegrityError:
                row = conn.execute(
                    """
                    SELECT raw_id FROM raw_transactions
                    WHERE account_source=? AND source_file=? AND row_number=?
                    """,
                    (source, source_file, tx.row_number),
                ).fetchone()
                raw_id = row[0]

            try:
                conn.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, raw_id, account_source, account_type,
                        transaction_date, post_date, description_raw,
                        amount, category_source, is_pending
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tx.transaction_id,
                        raw_id,
                        tx.account_source,
                        tx.account_type,
                        tx.transaction_date.isoformat(),
                        tx.post_date.isoformat() if tx.post_date else None,
                        tx.description_raw,
                        str(tx.amount),
                        tx.category_source,
                        int(tx.is_pending),
                    ),
                )
                rows_inserted += 1
            except sqlite3.IntegrityError:
                rows_skipped += 1

        conn.execute(
            """
            UPDATE ingestion_runs
            SET rows_read=?, rows_inserted=?, rows_skipped=?,
                completed_at=?, status='success'
            WHERE run_id=?
            """,
            (rows_read, rows_inserted, rows_skipped, datetime.now().isoformat(), run_id),
        )
        conn.commit()

    except Exception as exc:
        if run_id is not None:
            conn.execute(
                """
                UPDATE ingestion_runs
                SET completed_at=?, status='failed', error_message=?
                WHERE run_id=?
                """,
                (datetime.now().isoformat(), str(exc), run_id),
            )
            conn.commit()
        raise

    finally:
        conn.close()

    return {
        "source": source,
        "rows_read": rows_read,
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_skipped,
    }
