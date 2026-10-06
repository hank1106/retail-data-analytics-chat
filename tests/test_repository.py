"""Unit tests: repository aggregates vs an independent plain-Python oracle."""

from __future__ import annotations

import pytest


def _customer_rows(rows, customer_id, since=None):
    return [
        r for r in rows
        if r["customer_id"] == customer_id
        and (since is None or r["transaction_date"] >= since)
    ]


def _product_rows(rows, product_id, since=None):
    return [
        r for r in rows
        if r["product_id"] == product_id
        and (since is None or r["transaction_date"] >= since)
    ]


def test_customer_total_matches_oracle(repo, seed_rows):
    expected = round(sum(r["total_amount"] for r in _customer_rows(seed_rows, "C10001")), 2)
    got = repo.get_customer_total_spent("C10001")
    assert got["customer_id"] == "C10001"
    assert got["total_spent"] == pytest.approx(expected)
    assert got["transaction_count"] == len(_customer_rows(seed_rows, "C10001"))


def test_customer_purchases_shape_and_limit(repo, seed_rows):
    got = repo.get_customer_purchases("C10001", limit=5)
    assert got["transaction_count"] == len(_customer_rows(seed_rows, "C10001"))
    assert len(got["purchases"]) <= 5
    assert set(got["purchases"][0]) >= {"product_id", "total_amount", "transaction_date"}


def test_product_summary_matches_oracle(repo, seed_rows):
    rows = _product_rows(seed_rows, "P1001")
    expected_revenue = round(sum(r["total_amount"] for r in rows), 2)
    expected_discount = (
        round(sum(r["discount"] for r in rows) / len(rows), 4) if rows else 0.0
    )
    got = repo.get_product_summary("P1001")
    assert got["times_sold"] == len(rows)
    assert got["total_revenue"] == pytest.approx(expected_revenue)
    assert got["avg_discount"] == pytest.approx(expected_discount)
    assert got["stores"] == sorted({r["store_id"] for r in rows})


def test_overview_matches_oracle(repo, seed_rows):
    expected_revenue = round(sum(r["total_amount"] for r in seed_rows), 2)
    got = repo.get_overview()
    assert got["transaction_count"] == len(seed_rows)
    assert got["total_revenue"] == pytest.approx(expected_revenue)
    assert got["customer_count"] == len({r["customer_id"] for r in seed_rows})
    assert got["product_count"] == len({r["product_id"] for r in seed_rows})
    assert got["avg_basket"] == pytest.approx(round(expected_revenue / len(seed_rows), 2))


def test_top_products_ordering(repo, seed_rows):
    from collections import defaultdict

    revenue: dict[str, float] = defaultdict(float)
    for r in seed_rows:
        revenue[r["product_id"]] += r["total_amount"]
    expected = sorted(revenue, key=revenue.get, reverse=True)[:3]  # type: ignore[arg-type]
    got = [r["product_id"] for r in repo.top_products(3)]
    assert got == expected


def test_time_window_filters(repo, seed_rows):
    since = "2024-12-01"
    expected = _customer_rows(seed_rows, "C10001", since)
    got = repo.get_customer_purchases("C10001", since=since)
    assert got["transaction_count"] == len(expected)
    expected_total = round(sum(r["total_amount"] for r in expected), 2)
    assert got["total_spent"] == pytest.approx(expected_total)


def test_existence(repo):
    assert repo.customer_exists("C10001")
    assert not repo.customer_exists("C99999")
    assert repo.product_exists("P1001")
    assert not repo.product_exists("P9999")
