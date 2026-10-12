"""Chat orchestrator: parse -> query SQLite -> phrase the answer.

Every number in the reply comes from the database layer; the optional LLM
only rewords the precomputed template (see app/llm.py).
"""

from __future__ import annotations

import sqlite3

from . import db, llm
from .nlp import ParsedQuery, parse_query


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _txn_line(t: dict) -> str:
    return (
        f"- {t['transaction_date']}: {t['quantity']}x product {t['product_id']} "
        f"({t['product_category']}) at {t['store_location'].split(chr(10))[0]} — "
        f"{_money(t['total_amount'])} via {t['payment_method']}"
    )


def _customer_answer(summary: dict | None, customer_id: str) -> tuple[str, dict]:
    if summary is None:
        evidence = {"found": False, "customer_id": customer_id}
        text = (
            f"I couldn't find customer {customer_id} in the dataset. "
            "Customer IDs are numbers (you can write them with or without a "
            "leading C, e.g. C109318). Try a known ID such as 109318, 11111, or 12345."
        )
        return text, evidence
    evidence = {"found": True, **{k: v for k, v in summary.items() if k != "history"}}
    history = summary["history"][:10]
    lines = [_txn_line(t) for t in history]
    extra = "" if len(summary["history"]) <= 10 else f"\n(and {len(summary['history']) - 10} more)"
    text = (
        f"Customer {summary['customer_id']} made {summary['transactions']} purchase(s) "
        f"totaling {_money(summary['total_spent'])} "
        f"({summary['total_quantity']} items, avg discount {summary['avg_discount_pct']}%). "
        f"Categories: {', '.join(summary['categories'])}. "
        f"First purchase {summary['first_purchase']}, last {summary['last_purchase']}.\n"
        + "\n".join(lines) + extra
    )
    return text, evidence


def _product_answer(summary: dict | None, conn: sqlite3.Connection, product_id: str) -> tuple[str, dict]:
    if summary is None:
        valid = ", ".join(db.get_known_product_ids(conn))
        evidence = {"found": False, "product_id": product_id, "valid_ids": valid}
        text = (
            f"I couldn't find product {product_id} in the dataset. "
            f"Valid product IDs are: {valid}. "
            f"For example, try “What's the average discount for product C?”"
        )
        return text, evidence
    evidence = {"found": True, **{k: v for k, v in summary.items() if k != "stores_sample"}}
    stores = "; ".join(s.split("\n")[0] for s in summary["stores_sample"][:5])
    cats = ", ".join(f"{c['product_category']} ({c['n']})" for c in summary["categories"])
    text = (
        f"Product {summary['product_id']}: {summary['transactions']} transaction(s), "
        f"{summary['total_quantity']} units sold, {_money(summary['total_revenue'])} revenue, "
        f"average discount {summary['avg_discount_pct']}%, average price {_money(summary['avg_price'])}. "
        f"Categories: {cats}. Sold in {summary['store_count']} store(s), including: {stores}."
    )
    return text, evidence


def _business_answer(metrics: dict) -> tuple[str, dict]:
    if metrics["transactions"] == 0:
        return "No transactions match those filters. Try removing the category or payment filter.", metrics
    f = metrics["filters"]
    scope = "Overall"
    if f["category"] or f["payment_method"]:
        bits = [b for b in (f["category"], f["payment_method"]) if b]
        scope = f"Filtered ({', '.join(bits)})"
    cats = "; ".join(
        f"{c['product_category']}: {_money(c['revenue'])} ({c['transactions']} txns)"
        for c in metrics["revenue_by_category"]
    )
    pays = "; ".join(
        f"{p['payment_method']}: {_money(p['revenue'])}" for p in metrics["revenue_by_payment"]
    )
    tops = "; ".join(
        f"{c['customer_id']} ({_money(c['total_spent'])})" for c in metrics["top_customers"]
    )
    text = (
        f"{scope}: {metrics['transactions']} transactions, "
        f"{_money(metrics['total_revenue'])} total revenue, "
        f"{_money(metrics['avg_order_value'])} average order value, "
        f"{metrics['total_quantity']} items, avg discount {metrics['avg_discount_pct']}%.\n"
        f"Revenue by category — {cats}.\n"
        f"Revenue by payment — {pays}.\n"
        f"Top customers — {tops}."
    )
    return text, metrics


HELP_TEXT = (
    "I can answer questions about the retail transaction data. Try:\n"
    "- “What is the purchase history for customer C109318?”\n"
    "- “How much has customer C11111 spent in total?”\n"
    "- “What's the average discount for product C?”\n"
    "- “Which stores sell the product A?”\n"
    "- “What is the total revenue by category?”\n"
    "Customer IDs are numbers (optional C prefix, e.g. C12345); "
    "product IDs are A, B, C, D."
)

UNKNOWN_TEXT = (
    "I'm not sure what you're asking. I can look up a customer by ID "
    "(e.g. “How much has customer C11111 spent?”), a product by ID "
    "(e.g. “Which stores sell product C?”), or business metrics "
    "(e.g. “What is total revenue by category?”)."
)


def answer(conn: sqlite3.Connection, message: str) -> dict:
    """Full pipeline for one chat message. Always returns a response string."""
    parsed: ParsedQuery = parse_query(message)

    if parsed.intent == "help":
        return {"intent": "help", "entities": {}, "data": {}, "response": HELP_TEXT, "provider": "template"}

    if parsed.intent == "ambiguous":
        text = (
            f"That mentions both customer {parsed.customer_id} and product {parsed.product_id} — "
            "which one should I look up? Ask about the customer (e.g. "
            f"“purchase history for customer C{parsed.customer_id}”) or the product "
            f"(e.g. “average discount for product {parsed.product_id}”)."
        )
        return {
            "intent": "ambiguous",
            "entities": {"customer_id": parsed.customer_id, "product_id": parsed.product_id},
            "data": {}, "response": text, "provider": "template",
        }

    if parsed.intent == "customer":
        if not parsed.customer_id:
            text = ("Which customer? Please include a customer ID, e.g. "
                    "“What is the purchase history for customer C109318?”")
            return {"intent": "customer", "entities": {}, "data": {}, "response": text, "provider": "template"}
        template, evidence = _customer_answer(db.get_customer_summary(conn, parsed.customer_id), parsed.customer_id)
        response, provider = llm.rewrite(message, evidence, template)
        return {
            "intent": "customer",
            "entities": {"customer_id": parsed.customer_id},
            "data": evidence, "response": response, "provider": provider,
        }

    if parsed.intent == "product":
        if not parsed.product_id:
            text = ("Which product? Please include a product ID (A, B, C, or D), e.g. "
                    "“What's the average discount for product C?”")
            return {"intent": "product", "entities": {}, "data": {}, "response": text, "provider": "template"}
        template, evidence = _product_answer(db.get_product_summary(conn, parsed.product_id), conn, parsed.product_id)
        response, provider = llm.rewrite(message, evidence, template)
        return {
            "intent": "product",
            "entities": {"product_id": parsed.product_id},
            "data": evidence, "response": response, "provider": provider,
        }

    if parsed.intent == "business":
        metrics = db.get_business_metrics(conn, category=parsed.category, payment_method=parsed.payment_method)
        template, evidence = _business_answer(metrics)
        response, provider = llm.rewrite(message, evidence, template)
        return {
            "intent": "business",
            "entities": {"category": parsed.category, "payment_method": parsed.payment_method},
            "data": evidence, "response": response, "provider": provider,
        }

    return {"intent": "unknown", "entities": {}, "data": {}, "response": UNKNOWN_TEXT, "provider": "template"}
