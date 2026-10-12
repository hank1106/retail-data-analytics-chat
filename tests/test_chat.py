"""End-to-end tests: HTTP chat flow -> retrieval -> grounded response."""

from app import chat


def test_e2e_customer_query(client):
    r = client.post("/api/chat", json={"message": "How much has customer C11111 spent in total?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "customer"
    assert body["entities"] == {"customer_id": "11111"}
    assert body["data"]["total_spent"] == 157.00
    assert "$157.00" in body["response"]
    assert body["provider"] == "template"


def test_e2e_customer_purchase_history(client):
    r = client.post("/api/chat", json={"message": "What is the purchase history for customer C109318?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "customer"
    assert "$545.86" in body["response"]
    assert "Electronics" in body["response"]


def test_e2e_product_query(client):
    r = client.post("/api/chat", json={"message": "What's the average discount for product C?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "product"
    assert body["data"]["avg_discount_pct"] == 16.40
    assert "16.4" in body["response"]


def test_e2e_product_stores(client):
    r = client.post("/api/chat", json={"message": "Which stores sell the product A?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "product"
    assert body["data"]["store_count"] == 3
    assert "3 store(s)" in body["response"]


def test_e2e_business_question(client):
    r = client.post("/api/chat", json={"message": "What is the total revenue by category?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "business"
    assert body["data"]["total_revenue"] == 1412.19
    assert "1,412.19" in body["response"]
    assert "Books" in body["response"]


def test_e2e_invalid_customer_id(client):
    r = client.post("/api/chat", json={"message": "How much has customer C99999 spent?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "customer"
    assert body["data"]["found"] is False
    assert "couldn't find customer 99999" in body["response"]


def test_e2e_invalid_product_id_lists_valid_ids(client):
    r = client.post("/api/chat", json={"message": "Which stores sell the product P9999?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "product"
    assert body["data"]["found"] is False
    assert "A, B, C, D" in body["response"]


def test_e2e_empty_message_rejected(client):
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400


def test_e2e_rest_customer_summary(client):
    r = client.get("/api/customers/109318/summary")
    assert r.status_code == 200
    assert r.json()["total_spent"] == 545.86


def test_e2e_rest_unknown_customer_404(client):
    r = client.get("/api/customers/99999/summary")
    assert r.status_code == 404


def test_e2e_orchestrator_directly(conn):
    """Same pipeline without HTTP: parse -> SQL -> grounded text."""
    out = chat.answer(conn, "What is the purchase history for customer C109318?")
    assert out["intent"] == "customer"
    assert out["data"]["transactions"] == 2
    assert "$545.86" in out["response"]
