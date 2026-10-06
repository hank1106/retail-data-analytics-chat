"""Query processing: intent -> data retrieval -> natural language answer."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .intent import (
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
    ParsedQuery,
    missing_entity_hint,
    parse_query,
)
from .llm import Responder, TemplateProvider
from .repository import RetailRepository

EXAMPLE_QUERIES = [
    "What has customer C10001 purchased?",
    "How much has customer C10001 spent in total?",
    "What's the average discount for product P1001?",
    "Which stores sell the product P1001?",
    "What is the total revenue?",
    "Show me the top 5 products by revenue.",
]


def help_message() -> str:
    examples = "\n".join(f"- {q}" for q in EXAMPLE_QUERIES)
    return (
        "I can answer questions about customers, products and overall business "
        "metrics. Try one of these:\n" + examples
    )


@dataclass
class ChatResult:
    answer: str
    intent: str
    entities: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    ok: bool = True


def process_query(
    message: str,
    repo: RetailRepository,
    responder: Responder | None = None,
    today: dt.date | None = None,
) -> ChatResult:
    """Run the full pipeline for one user message."""
    responder = responder or Responder(primary=TemplateProvider())
    text = (message or "").strip()
    if not text:
        return ChatResult(
            answer="Please ask a question about a customer, product or the "
            "business. " + help_message(),
            intent=UNKNOWN,
            ok=False,
        )

    pq: ParsedQuery = parse_query(text, today)
    entities = {
        k: v
        for k, v in {
            "customer_id": pq.customer_id,
            "product_id": pq.product_id,
            "store_id": pq.store_id,
            "top_n": pq.top_n,
            "since": pq.since,
        }.items()
        if v is not None
    }
    window = {"window": pq.window_label} if pq.window_label else {}

    if pq.intent == HELP:
        return ChatResult(answer=help_message(), intent=HELP, entities=entities)
    if pq.intent == UNKNOWN:
        hint = missing_entity_hint(pq)
        if hint:
            return ChatResult(answer=hint, intent=UNKNOWN, entities=entities, ok=False)
        return ChatResult(
            answer="I couldn't tell whether that's about a customer, a product "
            "or business metrics. " + help_message(),
            intent=UNKNOWN,
            entities=entities,
            ok=False,
        )

    # -- customer intents -------------------------------------------------
    if pq.intent in (CUSTOMER_HISTORY, CUSTOMER_TOTAL, CUSTOMER_PRODUCT):
        assert pq.customer_id is not None
        if not repo.customer_exists(pq.customer_id):
            return ChatResult(
                answer=f"I couldn't find any record for customer {pq.customer_id}. "
                "Please check the ID and try again.",
                intent=pq.intent,
                entities=entities,
                ok=False,
            )
        if pq.intent == CUSTOMER_PRODUCT:
            assert pq.product_id is not None
            data = repo.customer_product_summary(
                pq.customer_id, pq.product_id, since=pq.since
            )
            if data["times_bought"] == 0:
                scope = f" {pq.window_label}" if pq.window_label else ""
                return ChatResult(
                    answer=f"Customer {pq.customer_id} has not bought product "
                    f"{pq.product_id}{scope}.",
                    intent=pq.intent,
                    entities=entities,
                    data={**data, **window},
                    ok=True,
                )
        elif pq.intent == CUSTOMER_TOTAL:
            data = repo.get_customer_total_spent(pq.customer_id, since=pq.since)
            if data["transaction_count"] == 0:
                return ChatResult(
                    answer=f"Customer {pq.customer_id} has no purchases"
                    + (f" in {pq.window_label}." if pq.window_label else "."),
                    intent=pq.intent,
                    entities=entities,
                    data={**data, **window},
                    ok=True,
                )
        else:
            data = repo.get_customer_purchases(
                pq.customer_id, since=pq.since
            )
            if data["transaction_count"] == 0:
                return ChatResult(
                    answer=f"Customer {pq.customer_id} has no purchases"
                    + (f" in {pq.window_label}." if pq.window_label else "."),
                    intent=pq.intent,
                    entities=entities,
                    data={**data, **window},
                    ok=True,
                )
        answer = responder.generate(
            question=text, intent=pq.intent, data={**data, **window}
        )
        return ChatResult(
            answer=answer, intent=pq.intent, entities=entities,
            data={**data, **window},
        )

    # -- product intents --------------------------------------------------
    if pq.intent in (PRODUCT_DISCOUNT, PRODUCT_STORES, PRODUCT_SUMMARY):
        assert pq.product_id is not None
        if not repo.product_exists(pq.product_id):
            return ChatResult(
                answer=f"I couldn't find any record for product {pq.product_id}. "
                "Please check the ID and try again.",
                intent=pq.intent,
                entities=entities,
                ok=False,
            )
        if pq.intent == PRODUCT_DISCOUNT:
            data = repo.get_product_summary(pq.product_id, since=pq.since)
            if data["times_sold"] == 0:
                return ChatResult(
                    answer=f"Product {pq.product_id} has no sales"
                    + (f" in {pq.window_label}." if pq.window_label else "."),
                    intent=pq.intent,
                    entities=entities,
                    data={**data, **window},
                    ok=True,
                )
        elif pq.intent == PRODUCT_STORES:
            data = repo.get_product_stores(pq.product_id, since=pq.since)
            if data["times_sold"] == 0:
                return ChatResult(
                    answer=f"Product {pq.product_id} has no sales"
                    + (f" in {pq.window_label}." if pq.window_label else "."),
                    intent=pq.intent,
                    entities=entities,
                    data={**data, **window},
                    ok=True,
                )
        else:
            data = repo.get_product_summary(pq.product_id, since=pq.since)
        answer = responder.generate(
            question=text, intent=pq.intent, data={**data, **window}
        )
        return ChatResult(
            answer=answer, intent=pq.intent, entities=entities,
            data={**data, **window},
        )

    # -- business intents -------------------------------------------------
    if pq.intent == BUSINESS_OVERVIEW:
        data = repo.get_overview(since=pq.since)
        answer = responder.generate(
            question=text, intent=pq.intent, data={**data, **window}
        )
        return ChatResult(
            answer=answer, intent=pq.intent, entities=entities,
            data={**data, **window},
        )
    if pq.intent == TOP_PRODUCTS:
        items = repo.top_products(pq.top_n, since=pq.since)
        data = {"items": items}
        answer = responder.generate(
            question=text, intent=pq.intent, data={**data, **window}
        )
        return ChatResult(
            answer=answer, intent=pq.intent, entities=entities,
            data={**data, **window},
        )
    if pq.intent == TOP_CUSTOMERS:
        items = repo.top_customers(pq.top_n, since=pq.since)
        data = {"items": items}
        answer = responder.generate(
            question=text, intent=pq.intent, data={**data, **window}
        )
        return ChatResult(
            answer=answer, intent=pq.intent, entities=entities,
            data={**data, **window},
        )
    if pq.intent == STORE_METRICS:
        stores = repo.revenue_by_store(since=pq.since)
        categories = repo.revenue_by_category(since=pq.since)
        data = {"stores": stores, "categories": categories}
        answer = responder.generate(
            question=text, intent=pq.intent, data={**data, **window}
        )
        return ChatResult(
            answer=answer, intent=pq.intent, entities=entities,
            data={**data, **window},
        )

    # Unreachable given the intent set above; fail closed.
    return ChatResult(
        answer="I couldn't handle that query. " + help_message(),
        intent=pq.intent,
        entities=entities,
        ok=False,
    )
