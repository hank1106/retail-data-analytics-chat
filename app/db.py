"""SQLite data-access layer for the retail transaction dataset.

The Kaggle CSV uses display column names (with spaces and a % sign); this
module normalizes them into a stable ``transactions`` table and exposes small,
typed query helpers used by the REST API and the chat orchestrator.

Real-data note: CustomerID values are plain numbers (e.g. ``109318``) and
ProductID values are single letters (``A``/``B``/``C``/``D``). IDs are stored
as TEXT so both forms query uniformly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    transaction_date TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    store_location TEXT NOT NULL,
    product_category TEXT NOT NULL,
    discount_pct REAL NOT NULL,
    total_amount REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_product ON transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_category ON transactions(product_category);
"""

COLUMNS = [
    "customer_id",
    "product_id",
    "quantity",
    "price",
    "transaction_date",
    "payment_method",
    "store_location",
    "product_category",
    "discount_pct",
    "total_amount",
]

# Kaggle header -> normalized column.
CSV_RENAME = {
    "CustomerID": "customer_id",
    "ProductID": "product_id",
    "Quantity": "quantity",
    "Price": "price",
    "TransactionDate": "transaction_date",
    "PaymentMethod": "payment_method",
    "StoreLocation": "store_location",
    "ProductCategory": "product_category",
    "DiscountApplied(%)": "discount_pct",
    "TotalAmount": "total_amount",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path, csv_path: str | Path) -> int:
    """Create schema and load ``csv_path``. Returns rows inserted."""
    import pandas as pd  # local import: only the loader needs pandas

    df = pd.read_csv(csv_path)
    missing = set(CSV_RENAME) - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing expected columns: {sorted(missing)}")
    df = df.rename(columns=CSV_RENAME)
    df["customer_id"] = df["customer_id"].astype(str).str.strip()
    df["product_id"] = df["product_id"].astype(str).str.strip().str.upper()

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM transactions")
        df[COLUMNS].to_sql("transactions", conn, if_exists="append", index=False)
        conn.commit()
        return int(len(df))
    finally:
        conn.close()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------- customers

def get_customer_transactions(conn: sqlite3.Connection, customer_id: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM transactions WHERE customer_id = ? ORDER BY transaction_date",
        (customer_id.strip(),),
    )


def get_customer_summary(conn: sqlite3.Connection, customer_id: str) -> dict | None:
    customer_id = customer_id.strip()
    txns = get_customer_transactions(conn, customer_id)
    if not txns:
        return None
    total_spent = round(sum(t["total_amount"] for t in txns), 2)
    return {
        "customer_id": customer_id,
        "transactions": len(txns),
        "total_spent": total_spent,
        "total_quantity": sum(t["quantity"] for t in txns),
        "avg_discount_pct": round(sum(t["discount_pct"] for t in txns) / len(txns), 2),
        "categories": sorted({t["product_category"] for t in txns}),
        "payment_methods": sorted({t["payment_method"] for t in txns}),
        "first_purchase": txns[0]["transaction_date"],
        "last_purchase": txns[-1]["transaction_date"],
        "history": txns,
    }


def get_customer_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(DISTINCT customer_id) FROM transactions").fetchone()[0])


# ----------------------------------------------------------------- products

def get_product_transactions(
    conn: sqlite3.Connection, product_id: str, limit: int = 50
) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM transactions WHERE product_id = ? ORDER BY transaction_date LIMIT ?",
        (product_id.strip().upper(), limit),
    )


def get_product_summary(conn: sqlite3.Connection, product_id: str) -> dict | None:
    product_id = product_id.strip().upper()
    row = conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(quantity),0) AS qty,
                  COALESCE(SUM(total_amount),0) AS revenue,
                  COALESCE(AVG(discount_pct),0) AS avg_discount,
                  COALESCE(AVG(price),0) AS avg_price,
                  COUNT(DISTINCT store_location) AS stores
           FROM transactions WHERE product_id = ?""",
        (product_id,),
    ).fetchone()
    if not row["n"]:
        return None
    stores = _rows(
        conn,
        "SELECT DISTINCT store_location FROM transactions WHERE product_id = ? LIMIT 10",
        (product_id,),
    )
    categories = _rows(
        conn,
        """SELECT product_category, COUNT(*) AS n FROM transactions
           WHERE product_id = ? GROUP BY product_category ORDER BY n DESC""",
        (product_id,),
    )
    return {
        "product_id": product_id,
        "transactions": row["n"],
        "total_quantity": row["qty"],
        "total_revenue": round(row["revenue"], 2),
        "avg_discount_pct": round(row["avg_discount"], 2),
        "avg_price": round(row["avg_price"], 2),
        "store_count": row["stores"],
        "stores_sample": [s["store_location"] for s in stores],
        "categories": categories,
    }


def get_known_product_ids(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT product_id FROM transactions ORDER BY 1").fetchall()]


# ------------------------------------------------------------------ business

def get_business_metrics(
    conn: sqlite3.Connection,
    category: str | None = None,
    payment_method: str | None = None,
) -> dict:
    filters, params = [], []
    if category:
        filters.append("product_category = ?")
        params.append(category)
    if payment_method:
        filters.append("payment_method = ?")
        params.append(payment_method)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    overall = conn.execute(
        f"""SELECT COUNT(*) AS n, COALESCE(SUM(total_amount),0) AS revenue,
                   COALESCE(AVG(total_amount),0) AS aov,
                   COALESCE(SUM(quantity),0) AS qty,
                   COALESCE(AVG(discount_pct),0) AS avg_discount
            FROM transactions {where}""",
        params,
    ).fetchone()

    by_category = _rows(
        conn,
        f"""SELECT product_category, COUNT(*) AS transactions,
                   ROUND(SUM(total_amount),2) AS revenue
            FROM transactions {where}
            GROUP BY product_category ORDER BY revenue DESC""",
        params,
    )
    by_payment = _rows(
        conn,
        f"""SELECT payment_method, COUNT(*) AS transactions,
                   ROUND(SUM(total_amount),2) AS revenue
            FROM transactions {where}
            GROUP BY payment_method ORDER BY revenue DESC""",
        params,
    )
    top_customers = _rows(
        conn,
        f"""SELECT customer_id, COUNT(*) AS transactions,
                   ROUND(SUM(total_amount),2) AS total_spent
            FROM transactions {where}
            GROUP BY customer_id ORDER BY total_spent DESC LIMIT 5""",
        params,
    )
    return {
        "filters": {"category": category, "payment_method": payment_method},
        "transactions": overall["n"],
        "total_revenue": round(overall["revenue"], 2),
        "avg_order_value": round(overall["aov"], 2),
        "total_quantity": overall["qty"],
        "avg_discount_pct": round(overall["avg_discount"], 2),
        "revenue_by_category": by_category,
        "revenue_by_payment": by_payment,
        "top_customers": top_customers,
    }


def get_known_categories(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT product_category FROM transactions ORDER BY 1").fetchall()]
