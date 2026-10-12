"""Unit tests: intent classification and entity extraction (app/nlp.py)."""

from app.nlp import parse_query


def test_customer_query_with_c_prefix():
    q = parse_query("What is the purchase history for customer C67890?")
    assert q.intent == "customer"
    assert q.customer_id == "67890"


def test_customer_total_spent():
    q = parse_query("How much has customer C11111 spent in total?")
    assert q.intent == "customer"
    assert q.customer_id == "11111"


def test_product_query_p_style_id_preserved_for_not_found():
    q = parse_query("What's the average discount for product P1234?")
    assert q.intent == "product"
    assert q.product_id == "1234"


def test_product_query_single_letter_id():
    q = parse_query("Which stores sell the product C?")
    assert q.intent == "product"
    assert q.product_id == "C"


def test_product_query_unknown_p_id_routes_to_product():
    q = parse_query("Which stores sell the product P9999?")
    assert q.intent == "product"
    assert q.product_id == "9999"


def test_business_query():
    q = parse_query("What is the total revenue by category?")
    assert q.intent == "business"


def test_business_query_with_category_filter():
    q = parse_query("How much revenue came from Electronics?")
    assert q.intent == "business"
    assert q.category == "Electronics"


def test_ambiguous_customer_and_product():
    q = parse_query("Compare customer 11111 with product C")
    assert q.intent == "ambiguous"
    assert q.customer_id == "11111"
    assert q.product_id == "C"


def test_customer_query_missing_id_asks_for_it():
    q = parse_query("Show me the purchase history")
    assert q.intent == "customer"
    assert q.customer_id is None


def test_unknown_query():
    q = parse_query("Tell me a joke about the weekend")
    assert q.intent == "unknown"


def test_greeting_routes_to_help():
    assert parse_query("hello").intent == "help"
    assert parse_query("What can you do?").intent == "help"
