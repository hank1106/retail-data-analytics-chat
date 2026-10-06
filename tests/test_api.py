"""API tests: REST data-access layer and the /api/chat endpoint."""

from __future__ import annotations


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_customer_endpoint(client):
    resp = client.get("/api/customers/C10001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == "C10001"
    assert body["transaction_count"] >= len(body["purchases"]) > 0


def test_customer_unknown_404(client):
    assert client.get("/api/customers/C99999").status_code == 404


def test_product_endpoint(client):
    resp = client.get("/api/products/P1001")
    assert resp.status_code == 200
    assert resp.json()["product_id"] == "P1001"


def test_product_stores_endpoint(client):
    resp = client.get("/api/products/P1001/stores")
    assert resp.status_code == 200
    assert resp.json()["stores"]


def test_product_unknown_404(client):
    assert client.get("/api/products/P9999").status_code == 404


def test_metrics_overview(client):
    body = client.get("/api/metrics/overview").json()
    assert {"total_revenue", "transaction_count", "avg_basket"} <= set(body)


def test_metrics_top_products(client):
    body = client.get("/api/metrics/top-products?n=3").json()
    assert len(body["items"]) == 3


def test_chat_customer_flow(client):
    body = client.post(
        "/api/chat", json={"message": "What has customer C10001 purchased?"}
    ).json()
    assert body["ok"] is True
    assert body["intent"] == "customer_history"
    assert "C10001" in body["answer"]


def test_chat_product_flow(client):
    body = client.post(
        "/api/chat", json={"message": "Which stores sell the product P1001?"}
    ).json()
    assert body["ok"] is True
    assert body["intent"] == "product_stores"


def test_chat_business_flow(client):
    body = client.post(
        "/api/chat", json={"message": "What is the total revenue?"}
    ).json()
    assert body["ok"] is True
    assert body["intent"] == "business_overview"
    assert "$" in body["answer"]


def test_chat_unknown_customer(client):
    body = client.post(
        "/api/chat", json={"message": "What has customer C99999 purchased?"}
    ).json()
    assert body["ok"] is False
