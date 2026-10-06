"""Unit tests: intent classification, entity extraction, time windows."""

from __future__ import annotations

import datetime as dt

import pytest

from retail_chat.intent import (
    BUSINESS_OVERVIEW,
    CUSTOMER_HISTORY,
    CUSTOMER_PRODUCT,
    CUSTOMER_TOTAL,
    HELP,
    PRODUCT_DISCOUNT,
    PRODUCT_STORES,
    PRODUCT_SUMMARY,
    STORE_METRICS,
    TOP_CUSTOMERS,
    TOP_PRODUCTS,
    UNKNOWN,
    parse_query,
)

TODAY = dt.date(2025, 6, 15)


@pytest.mark.parametrize(
    "question, intent, customer, product",
    [
        # Core assignment queries
        ("What is the purchase history for customer C67890?", CUSTOMER_HISTORY, "C67890", None),
        ("How much has customer C11111 spent in total?", CUSTOMER_TOTAL, "C11111", None),
        ("What's the average discount for product P1234?", PRODUCT_DISCOUNT, None, "P1234"),
        ("Which stores sell the product P9999?", PRODUCT_STORES, None, "P9999"),
        ("What has customer C12345 purchased?", CUSTOMER_HISTORY, "C12345", None),
        # More customer phrasings
        ("Show orders for customer C10001", CUSTOMER_HISTORY, "C10001", None),
        ("Total spent by customer C10002?", CUSTOMER_TOTAL, "C10002", None),
        ("how much is customer c10003 worth", CUSTOMER_TOTAL, "C10003", None),
        # More product phrasings
        ("Tell me about product P1001", PRODUCT_SUMMARY, None, "P1001"),
        ("Where is item P1002 sold?", PRODUCT_STORES, None, "P1002"),
        ("discount on P1005?", PRODUCT_DISCOUNT, None, "P1005"),
        # Intersection
        ("Did customer C10001 buy product P1001?", CUSTOMER_PRODUCT, "C10001", "P1001"),
        # Business questions
        ("What is the total revenue?", BUSINESS_OVERVIEW, None, None),
        ("Give me a business overview", BUSINESS_OVERVIEW, None, None),
        ("Show me the top 5 products by revenue", TOP_PRODUCTS, None, None),
        ("Top 10 customers by spending", TOP_CUSTOMERS, None, None),
        ("revenue by store", STORE_METRICS, None, None),
        ("What is the average basket size?", BUSINESS_OVERVIEW, None, None),
        # Help
        ("help", HELP, None, None),
        ("What can you do?", HELP, None, None),
        # Unanswerable
        ("What's the weather like?", UNKNOWN, None, None),
    ],
)
def test_classification(question, intent, customer, product):
    pq = parse_query(question, TODAY)
    assert pq.intent == intent, f"{question!r} -> {pq.intent}"
    assert pq.customer_id == customer
    assert pq.product_id == product


def test_top_n_extraction():
    assert parse_query("top 10 products", TODAY).top_n == 10
    assert parse_query("top products", TODAY).top_n == 5


def test_last_days_window():
    pq = parse_query("sales in the last 30 days", TODAY)
    assert pq.intent == BUSINESS_OVERVIEW
    assert pq.since == "2025-05-16"
    assert pq.window_label == "the last 30 days"


def test_month_window():
    pq = parse_query("revenue in March 2024", TODAY)
    assert pq.since == "2024-03-01"
    assert pq.window_label == "March 2024"


def test_year_like_product_id_is_not_a_window():
    pq = parse_query("Tell me about product P2024", TODAY)
    assert pq.intent == PRODUCT_SUMMARY
    assert pq.product_id == "P2024"
    assert pq.since is None
