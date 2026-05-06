import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parents[3] / "data" / "budgeting.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
