"""End-to-end tests: natural language query -> retrieval -> answer."""

from __future__ import annotations

import datetime as dt

import pytest

from retail_chat.intent import (
    BUSINESS_OVERVIEW,
    CUSTOMER_HISTORY,
    CUSTOMER_TOTAL,
    PRODUCT_DISCOUNT,
    PRODUCT_STORES,
)
from retail_chat.llm import LLMError, Responder, TemplateProvider
from retail_chat.service import process_query

TODAY = dt.date(2025, 6, 15)


def test_e2e_customer_history(repo, responder, seed_rows):
    result = process_query("What has customer C10001 purchased?", repo, responder, TODAY)
    assert result.ok
    assert result.intent == CUSTOMER_HISTORY
    assert result.entities["customer_id"] == "C10001"
    assert "C10001" in result.answer
    expected_total = round(
        sum(r["total_amount"] for r in seed_rows if r["customer_id"] == "C10001"), 2
    )
    assert result.data["total_spent"] == pytest.approx(expected_total)


def test_e2e_customer_total(repo, responder):
    result = process_query(
        "How much has customer C10001 spent in total?", repo, responder, TODAY
    )
    assert result.ok
    assert result.intent == CUSTOMER_TOTAL
    assert f"${result.data['total_spent']:,.2f}" in result.answer


def test_e2e_product_discount(repo, responder, seed_rows):
    result = process_query(
        "What's the average discount for product P1001?", repo, responder, TODAY
    )
    assert result.ok
    assert result.intent == PRODUCT_DISCOUNT
    rows = [r for r in seed_rows if r["product_id"] == "P1001"]
    expected = sum(r["discount"] for r in rows) / len(rows)
    assert result.data["avg_discount"] == pytest.approx(expected)
    assert f"{expected * 100:.1f}%" in result.answer


def test_e2e_product_stores(repo, responder, seed_rows):
    result = process_query(
        "Which stores sell the product P1001?", repo, responder, TODAY
    )
    assert result.ok
    assert result.intent == PRODUCT_STORES
    expected_stores = sorted({r["store_id"] for r in seed_rows if r["product_id"] == "P1001"})
    assert result.data["stores"] == expected_stores
    for store in expected_stores:
        assert store in result.answer


def test_e2e_business_overview(repo, responder, seed_rows):
    result = process_query("What is the total revenue?", repo, responder, TODAY)
    assert result.ok
    assert result.intent == BUSINESS_OVERVIEW
    expected = round(sum(r["total_amount"] for r in seed_rows), 2)
    assert result.data["total_revenue"] == pytest.approx(expected)
    assert f"${expected:,.2f}" in result.answer


def test_e2e_unknown_customer(repo, responder):
    result = process_query(
        "What has customer C99999 purchased?", repo, responder, TODAY
    )
    assert not result.ok
    assert "C99999" in result.answer


def test_e2e_unknown_product(repo, responder):
    result = process_query(
        "Which stores sell product P9999?", repo, responder, TODAY
    )
    assert not result.ok
    assert "P9999" in result.answer


def test_e2e_missing_customer_id(repo, responder):
    result = process_query("How much has the customer spent?", repo, responder, TODAY)
    assert not result.ok
    assert "C10001" in result.answer  # asks for an ID like C10001


def test_e2e_empty_and_gibberish(repo, responder):
    assert not process_query("", repo, responder, TODAY).ok
    assert not process_query("What's the weather?", repo, responder, TODAY).ok


def test_e2e_empty_time_window(repo, responder):
    # Seed data is all in 2024; "last 30 days" from TODAY is empty.
    result = process_query(
        "How much has customer C10001 spent in the last 30 days?",
        repo,
        responder,
        TODAY,
    )
    assert result.ok
    assert result.data["transaction_count"] == 0
    assert "no purchases" in result.answer


def test_e2e_llm_failure_falls_back_to_template(repo, seed_rows):
    class BrokenProvider(TemplateProvider):
        name = "broken"

        def generate(self, *, question, intent, data):
            raise LLMError("boom")

    responder = Responder(primary=BrokenProvider())
    result = process_query("What is the total revenue?", repo, responder, TODAY)
    assert result.ok
    assert "$" in result.answer
