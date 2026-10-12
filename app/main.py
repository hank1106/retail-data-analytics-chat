"""FastAPI backend: REST data API + chat endpoint + static chat UI."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import chat, db, llm

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("RETAIL_DB", ROOT / "data" / "retail.db"))
CSV_PATH = Path(os.getenv("RETAIL_CSV", ROOT / "data" / "sample_transactions.csv"))

app = FastAPI(title="Retail Data Analytics Chat")


def get_conn():
    if not DB_PATH.exists():
        # First run without the Kaggle download: seed from the bundled sample
        # so the API and UI work immediately after clone.
        db.init_db(DB_PATH, CSV_PATH)
    return db.connect(DB_PATH)


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
def health() -> dict:
    conn = get_conn()
    try:
        return {
            "status": "ok",
            "transactions": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            "customers": db.get_customer_count(conn),
            "products": db.get_known_product_ids(conn),
            "llm": llm.provider_status(),
        }
    finally:
        conn.close()


@app.get("/api/customers/{customer_id}")
def customer_transactions(customer_id: str):
    conn = get_conn()
    try:
        txns = db.get_customer_transactions(conn, customer_id)
        if not txns:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        return {"customer_id": customer_id, "transactions": txns}
    finally:
        conn.close()


@app.get("/api/customers/{customer_id}/summary")
def customer_summary(customer_id: str):
    conn = get_conn()
    try:
        summary = db.get_customer_summary(conn, customer_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        return summary
    finally:
        conn.close()


@app.get("/api/products/{product_id}")
def product_transactions(product_id: str, limit: int = 50):
    conn = get_conn()
    try:
        txns = db.get_product_transactions(conn, product_id, limit)
        if not txns:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found. Valid IDs: {db.get_known_product_ids(conn)}",
            )
        return {"product_id": product_id.upper(), "transactions": txns}
    finally:
        conn.close()


@app.get("/api/products/{product_id}/summary")
def product_summary(product_id: str):
    conn = get_conn()
    try:
        summary = db.get_product_summary(conn, product_id)
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found. Valid IDs: {db.get_known_product_ids(conn)}",
            )
        return summary
    finally:
        conn.close()


@app.get("/api/metrics")
def metrics(category: str | None = None, payment_method: str | None = None):
    conn = get_conn()
    try:
        return db.get_business_metrics(conn, category=category, payment_method=payment_method)
    finally:
        conn.close()


@app.get("/api/examples")
def examples() -> dict:
    return {
        "customer": [
            "What is the purchase history for customer C109318?",
            "How much has customer C11111 spent in total?",
        ],
        "product": [
            "What's the average discount for product C?",
            "Which stores sell the product A?",
        ],
        "business": [
            "What is the total revenue by category?",
            "What is the average order value?",
            "Who are the top customers by spend?",
        ],
    }


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty")
    conn = get_conn()
    try:
        return chat.answer(conn, req.message.strip())
    finally:
        conn.close()


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")
