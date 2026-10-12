"""Unit tests: SQLite data-access layer (app/db.py) against the sample CSV."""

from app import db


def test_customer_summary_totals(conn):
    s = db.get_customer_summary(conn, "109318")
    assert s is not None
    assert s["transactions"] == 2
    assert s["total_spent"] == 545.86
    assert s["total_quantity"] == 9
    assert set(s["categories"]) == {"Books", "Electronics"}


def test_customer_summary_single_purchase(conn):
    s = db.get_customer_summary(conn, "11111")
    assert s is not None
    assert s["transactions"] == 2
    assert s["total_spent"] == 157.00


def test_customer_not_found(conn):
    assert db.get_customer_summary(conn, "99999") is None
    assert db.get_customer_transactions(conn, "99999") == []


def test_product_summary(conn):
    s = db.get_product_summary(conn, "C")
    assert s is not None
    assert s["transactions"] == 2
    assert s["avg_discount_pct"] == 16.40
    assert s["store_count"] == 2


def test_product_summary_revenue(conn):
    s = db.get_product_summary(conn, "A")
    assert s is not None
    assert s["transactions"] == 3
    assert s["total_revenue"] == 254.52
    assert s["store_count"] == 3


def test_product_not_found(conn):
    assert db.get_product_summary(conn, "Z") is None


def test_business_metrics_overall(conn):
    m = db.get_business_metrics(conn)
    assert m["transactions"] == 9
    assert m["total_revenue"] == 1412.19
    assert m["avg_order_value"] == round(1412.19 / 9, 2)
    assert len(m["revenue_by_category"]) == 4
    assert len(m["top_customers"]) == 5
    assert m["top_customers"][0]["customer_id"] == "109318"


def test_business_metrics_category_filter(conn):
    m = db.get_business_metrics(conn, category="Books")
    assert m["transactions"] == 3
    assert m["total_revenue"] == 832.36
