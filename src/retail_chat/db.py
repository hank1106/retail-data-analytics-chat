"""SQLite helpers: connection management and schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id   TEXT,
    customer_id      TEXT NOT NULL,
    product_id       TEXT NOT NULL,
    store_id         TEXT,
    quantity         INTEGER,
    unit_price       REAL,
    discount         REAL,
    total_amount     REAL,
    transaction_date TEXT,
    payment_method   TEXT,
    product_category TEXT
);
CREATE INDEX IF NOT EXISTS idx_tx_customer ON transactions (customer_id);
CREATE INDEX IF NOT EXISTS idx_tx_product ON transactions (product_id);
CREATE INDEX IF NOT EXISTS idx_tx_store ON transactions (store_id);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions (transaction_date);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the SQLite database, creating parent dirs as needed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
