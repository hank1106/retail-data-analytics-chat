"""Data access layer: customer, product and business-metric queries."""

from __future__ import annotations

import sqlite3


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def _date_filter(since: str | None) -> tuple[str, list]:
    if since:
        return " AND transaction_date >= ?", [since]
    return "", []


class RetailRepository:
    """Read-only queries over the ``transactions`` table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- existence -----------------------------------------------------
    def customer_exists(self, customer_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM transactions WHERE customer_id = ? LIMIT 1",
            (customer_id,),
        ).fetchone()
        return row is not None

    def product_exists(self, product_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM transactions WHERE product_id = ? LIMIT 1",
            (product_id,),
        ).fetchone()
        return row is not None

    # -- customer ------------------------------------------------------
    def get_customer_purchases(
        self, customer_id: str, limit: int = 20, since: str | None = None
    ) -> dict:
        extra, params = _date_filter(since)
        purchases = _rows(
            self.conn.execute(
                "SELECT transaction_id, product_id, store_id, quantity,"
                " unit_price, discount, total_amount, transaction_date,"
                " payment_method, product_category"
                " FROM transactions WHERE customer_id = ?"
                f"{extra} ORDER BY transaction_date DESC LIMIT ?",
                (customer_id, *params, limit),
            )
        )
        agg = self.conn.execute(
            "SELECT COUNT(*), COALESCE(ROUND(SUM(total_amount), 2), 0)"
            f" FROM transactions WHERE customer_id = ?{extra}",
            (customer_id, *params),
        ).fetchone()
        return {
            "customer_id": customer_id,
            "transaction_count": agg[0],
            "total_spent": agg[1],
            "purchases": purchases,
        }

    def get_customer_total_spent(
        self, customer_id: str, since: str | None = None
    ) -> dict:
        summary = self.get_customer_purchases(customer_id, limit=1, since=since)
        return {
            "customer_id": customer_id,
            "transaction_count": summary["transaction_count"],
            "total_spent": summary["total_spent"],
        }

    def customer_product_summary(
        self, customer_id: str, product_id: str, since: str | None = None
    ) -> dict:
        extra, params = _date_filter(since)
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity), 0),"
            " COALESCE(ROUND(SUM(total_amount), 2), 0)"
            " FROM transactions"
            f" WHERE customer_id = ? AND product_id = ?{extra}",
            (customer_id, product_id, *params),
        ).fetchone()
        return {
            "customer_id": customer_id,
            "product_id": product_id,
            "times_bought": row[0],
            "total_quantity": row[1],
            "total_spent": row[2],
        }

    # -- product -------------------------------------------------------
    def get_product_summary(
        self, product_id: str, since: str | None = None
    ) -> dict:
        extra, params = _date_filter(since)
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity), 0),"
            " COALESCE(ROUND(SUM(total_amount), 2), 0),"
            " ROUND(AVG(discount), 4)"
            " FROM transactions"
            f" WHERE product_id = ?{extra}",
            (product_id, *params),
        ).fetchone()
        stores = [
            r["store_id"]
            for r in _rows(
                self.conn.execute(
                    "SELECT DISTINCT store_id FROM transactions"
                    f" WHERE product_id = ?{extra} AND store_id IS NOT NULL"
                    " ORDER BY store_id",
                    (product_id, *params),
                )
            )
        ]
        return {
            "product_id": product_id,
            "times_sold": row[0],
            "total_quantity": row[1],
            "total_revenue": row[2],
            "avg_discount": row[3] or 0.0,
            "stores": stores,
        }

    def get_product_stores(
        self, product_id: str, since: str | None = None
    ) -> dict:
        summary = self.get_product_summary(product_id, since=since)
        return {
            "product_id": product_id,
            "stores": summary["stores"],
            "times_sold": summary["times_sold"],
        }

    # -- business metrics ----------------------------------------------
    def get_overview(self, since: str | None = None) -> dict:
        extra, params = _date_filter(since)
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(ROUND(SUM(total_amount), 2), 0),"
            " COUNT(DISTINCT customer_id), COUNT(DISTINCT product_id),"
            " COUNT(DISTINCT store_id)"
            f" FROM transactions WHERE 1 = 1{extra}",
            params,
        ).fetchone()
        count = row[0]
        return {
            "transaction_count": count,
            "total_revenue": row[1],
            "customer_count": row[2],
            "product_count": row[3],
            "store_count": row[4],
            "avg_basket": round(row[1] / count, 2) if count else 0.0,
        }

    def top_products(self, n: int = 5, since: str | None = None) -> list[dict]:
        extra, params = _date_filter(since)
        return _rows(
            self.conn.execute(
                "SELECT product_id,"
                " COALESCE(ROUND(SUM(total_amount), 2), 0) AS revenue,"
                " COUNT(*) AS times_sold"
                f" FROM transactions WHERE 1 = 1{extra}"
                " GROUP BY product_id ORDER BY revenue DESC LIMIT ?",
                (*params, n),
            )
        )

    def top_customers(self, n: int = 5, since: str | None = None) -> list[dict]:
        extra, params = _date_filter(since)
        return _rows(
            self.conn.execute(
                "SELECT customer_id,"
                " COALESCE(ROUND(SUM(total_amount), 2), 0) AS total_spent,"
                " COUNT(*) AS transactions"
                f" FROM transactions WHERE 1 = 1{extra}"
                " GROUP BY customer_id ORDER BY total_spent DESC LIMIT ?",
                (*params, n),
            )
        )

    def revenue_by_store(self, since: str | None = None) -> list[dict]:
        extra, params = _date_filter(since)
        return _rows(
            self.conn.execute(
                "SELECT store_id,"
                " COALESCE(ROUND(SUM(total_amount), 2), 0) AS revenue,"
                " COUNT(*) AS transactions"
                f" FROM transactions WHERE store_id IS NOT NULL{extra}"
                " GROUP BY store_id ORDER BY revenue DESC",
                params,
            )
        )

    def revenue_by_category(self, since: str | None = None) -> list[dict]:
        extra, params = _date_filter(since)
        return _rows(
            self.conn.execute(
                "SELECT product_category,"
                " COALESCE(ROUND(SUM(total_amount), 2), 0) AS revenue,"
                " COUNT(*) AS transactions"
                f" FROM transactions WHERE product_category IS NOT NULL{extra}"
                " GROUP BY product_category ORDER BY revenue DESC",
                params,
            )
        )
