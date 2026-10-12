"""Deterministic intent classification and entity extraction.

Rule-based on purpose: IDs and routing decisions must be exact and testable,
so the LLM (when configured) is only ever used to phrase the final answer —
never to decide what the user asked for or which IDs to look up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CUSTOMER_PATTERNS = [
    re.compile(r"\bcustomer\s*(?:id)?\s*:?\s*#?\s*c-?(\d{2,10})\b", re.I),
    re.compile(r"\bc-?(\d{2,10})\b"),
    re.compile(r"\bcustomer\s*(?:id)?\s*:?\s*#?\s*(\d{2,10})\b", re.I),
    re.compile(r"\bclient\s+(\d{2,10})\b", re.I),
]

PRODUCT_PATTERNS = [
    # Real IDs are single letters (A-D); P-prefixed numeric forms (P9999,
    # P1234) are captured too so we can report "not found" instead of
    # misrouting. The bare-P fallback is digits-only: a loose "P+letters"
    # pattern would match words like "product" or "purchase" themselves.
    re.compile(r"\bproduct\s*(?:id)?\s*:?\s*#?\s*p-?([A-Za-z0-9]{1,8})\b", re.I),
    re.compile(r"\bP-?(\d{2,8})\b"),
    re.compile(r"\bproduct\s*(?:id)?\s*:?\s*#?\s*([A-Za-z])\b", re.I),
    re.compile(r"\bitem\s+([A-Za-z0-9]{1,8})\b", re.I),
]

KNOWN_CATEGORIES = ["Books", "Clothing", "Electronics", "Home Decor"]
KNOWN_PAYMENTS = ["Cash", "Credit Card", "Debit Card", "PayPal"]

BUSINESS_KEYWORDS = [
    "total revenue", "revenue", "total sales", "sales", "business",
    "overall", "average order", "avg order", "aov",
    "how many transactions", "number of transactions", "transaction count",
    "top customer", "top spender", "best customer", "best-selling",
    "best seller", "category performance", "by category", "per category",
    "payment mix", "payment method", "kpi", "metrics", "summary of",
    "overview", "all customers", "entire store", "whole store",
]

CUSTOMER_KEYWORDS = [
    "customer", "client", "purchase history", "purchase record",
    "what did", "what has", "bought", "purchased", "spent", "spend",
    "who is",
]

PRODUCT_KEYWORDS = [
    "product", "item", "sku", "stores sell", "which stores", "where is",
    "discount for", "average discount", "price of",
]

HELP_PATTERNS = [
    r"^\s*(hi|hello|hey|yo)\b", r"\bhelp\b", r"what can you do",
    r"^\s*(thanks|thank you|bye|goodbye)\b",
]

ASPECT_KEYWORDS = {
    "history": ["purchase history", "history", "bought", "purchased", "what did", "what has", "transactions for", "orders"],
    "total": ["how much", "total spent", "spent", "spend", "total"],
    "stores": ["which stores", "stores sell", "where", "store"],
    "discount": ["discount", "promotion", "offer"],
}


@dataclass
class ParsedQuery:
    intent: str  # customer | product | business | ambiguous | help | unknown
    customer_id: str | None = None
    product_id: str | None = None
    category: str | None = None
    payment_method: str | None = None
    top_n: int | None = None
    aspects: list[str] = field(default_factory=list)


def _find(patterns: list[re.Pattern], text: str) -> str | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def _match_option(text: str, options: list[str]) -> str | None:
    lowered = text.lower()
    for opt in options:
        if opt.lower() in lowered:
            return opt
    return None


def parse_query(text: str) -> ParsedQuery:
    text = text or ""
    lowered = text.lower().strip()

    for pat in HELP_PATTERNS:
        if re.search(pat, lowered):
            return ParsedQuery(intent="help")

    raw_customer = _find(CUSTOMER_PATTERNS, text)
    raw_product = _find(PRODUCT_PATTERNS, text)
    # A bare "product C" style ID can also match CUSTOMER's C-prefix rule
    # (e.g. "product C"); if the word "product"/"item" is adjacent to it,
    # it is a product ID, not a customer ID.
    if raw_customer and re.search(r"(product|item)\s*:?\s*#?\s*c-?\d+", text, re.I):
        raw_product = raw_product or raw_customer
        raw_customer = None

    customer_id = raw_customer.upper().lstrip("C") if raw_customer else None
    # Normalize: "C109318" -> "109318"; keep pure digits as-is.
    if customer_id is not None:
        customer_id = re.sub(r"^C", "", customer_id.upper())
    product_id = raw_product.upper() if raw_product else None

    category = _match_option(text, KNOWN_CATEGORIES)
    payment_method = _match_option(text, KNOWN_PAYMENTS)
    top_m = re.search(r"\btop\s+(\d{1,2})\b", lowered)
    top_n = int(top_m.group(1)) if top_m else None

    aspects = [name for name, kws in ASPECT_KEYWORDS.items() if any(k in lowered for k in kws)]

    has_business_kw = any(k in lowered for k in BUSINESS_KEYWORDS)
    has_customer_kw = any(k in lowered for k in CUSTOMER_KEYWORDS)
    has_product_kw = any(k in lowered for k in PRODUCT_KEYWORDS)

    if customer_id and product_id:
        return ParsedQuery(
            intent="ambiguous", customer_id=customer_id, product_id=product_id,
            category=category, payment_method=payment_method, top_n=top_n, aspects=aspects,
        )
    if customer_id:
        return ParsedQuery(
            intent="customer", customer_id=customer_id, category=category,
            payment_method=payment_method, aspects=aspects,
        )
    if product_id:
        return ParsedQuery(
            intent="product", product_id=product_id, category=category, aspects=aspects,
        )
    if has_business_kw or (category and not (has_customer_kw or has_product_kw)):
        return ParsedQuery(
            intent="business", category=category, payment_method=payment_method,
            top_n=top_n, aspects=aspects,
        )
    if has_customer_kw:
        return ParsedQuery(intent="customer", aspects=aspects)  # ID missing -> ask
    if has_product_kw:
        return ParsedQuery(intent="product", aspects=aspects)  # ID missing -> ask
    return ParsedQuery(intent="unknown")
