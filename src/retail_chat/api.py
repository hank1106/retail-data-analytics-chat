"""REST data-access layer + conversational endpoint (FastAPI).

Run with::

    uvicorn retail_chat.api:app --reload
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from .config import Settings
from .data_loader import ensure_database
from .db import connect
from .llm import Responder, build_responder
from .repository import RetailRepository
from .service import ChatResult, process_query


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    intent: str
    entities: dict = {}
    data: dict = {}
    ok: bool = True


def _result_to_response(result: ChatResult) -> ChatResponse:
    return ChatResponse(
        answer=result.answer,
        intent=result.intent,
        entities=result.entities,
        data=result.data,
        ok=result.ok,
    )


def create_app(
    db_path: str | Path | None = None, settings: Settings | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    requested_db = db_path

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # One connection per request (SQLite connections are thread-bound),
        # so lifespan only guarantees the database exists.
        app.state.db_path = str(ensure_database(requested_db))
        app.state.responder = build_responder(settings)
        yield

    app = FastAPI(title="Retail Data Analytics Chat System", lifespan=lifespan)

    def get_repo() -> Iterator[RetailRepository]:
        conn = connect(app.state.db_path)
        try:
            yield RetailRepository(conn)
        finally:
            conn.close()

    def responder() -> Responder:
        return app.state.responder

    @app.get("/api/health")
    def health():
        return {"status": "ok", "provider": app.state.responder.primary.name}

    @app.get("/api/customers/{customer_id}")
    def customer_purchases(
        customer_id: str,
        repo: RetailRepository = Depends(get_repo),
        limit: int = Query(20, ge=1, le=200),
        since: str | None = None,
    ):
        customer_id = customer_id.upper()
        if not repo.customer_exists(customer_id):
            raise HTTPException(404, f"Unknown customer: {customer_id}")
        return repo.get_customer_purchases(customer_id, limit=limit, since=since)

    @app.get("/api/customers/{customer_id}/total")
    def customer_total(
        customer_id: str,
        repo: RetailRepository = Depends(get_repo),
        since: str | None = None,
    ):
        customer_id = customer_id.upper()
        if not repo.customer_exists(customer_id):
            raise HTTPException(404, f"Unknown customer: {customer_id}")
        return repo.get_customer_total_spent(customer_id, since=since)

    @app.get("/api/products/{product_id}")
    def product_summary(
        product_id: str,
        repo: RetailRepository = Depends(get_repo),
        since: str | None = None,
    ):
        product_id = product_id.upper()
        if not repo.product_exists(product_id):
            raise HTTPException(404, f"Unknown product: {product_id}")
        return repo.get_product_summary(product_id, since=since)

    @app.get("/api/products/{product_id}/stores")
    def product_stores(
        product_id: str,
        repo: RetailRepository = Depends(get_repo),
        since: str | None = None,
    ):
        product_id = product_id.upper()
        if not repo.product_exists(product_id):
            raise HTTPException(404, f"Unknown product: {product_id}")
        return repo.get_product_stores(product_id, since=since)

    @app.get("/api/metrics/overview")
    def metrics_overview(
        repo: RetailRepository = Depends(get_repo), since: str | None = None
    ):
        return repo.get_overview(since=since)

    @app.get("/api/metrics/top-products")
    def metrics_top_products(
        repo: RetailRepository = Depends(get_repo),
        n: int = Query(5, ge=1, le=50),
        since: str | None = None,
    ):
        return {"items": repo.top_products(n, since=since)}

    @app.get("/api/metrics/top-customers")
    def metrics_top_customers(
        repo: RetailRepository = Depends(get_repo),
        n: int = Query(5, ge=1, le=50),
        since: str | None = None,
    ):
        return {"items": repo.top_customers(n, since=since)}

    @app.get("/api/metrics/by-store")
    def metrics_by_store(
        repo: RetailRepository = Depends(get_repo), since: str | None = None
    ):
        return {
            "stores": repo.revenue_by_store(since=since),
            "categories": repo.revenue_by_category(since=since),
        }

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        repo: RetailRepository = Depends(get_repo),
        chat_responder: Responder = Depends(responder),
    ):
        result = process_query(request.message, repo, chat_responder)
        return _result_to_response(result)

    return app


app = create_app()
