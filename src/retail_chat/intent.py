"""Query understanding: intent classification and entity extraction.

Rule-based and dependency-free, so intent routing works with no LLM and no
network. The LLM layer (``llm.py``) only turns retrieved facts into prose.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

# Intent names -------------------------------------------------------------
CUSTOMER_HISTORY = "customer_history"
CUSTOMER_TOTAL = "customer_total"
CUSTOMER_PRODUCT = "customer_product"
PRODUCT_DISCOUNT = "product_discount"
PRODUCT_STORES = "product_stores"
PRODUCT_SUMMARY = "product_summary"
BUSINESS_OVERVIEW = "business_overview"
TOP_PRODUCTS = "top_products"
TOP_CUSTOMERS = "top_customers"
STORE_METRICS = "store_metrics"
HELP = "help"
UNKNOWN = "unknown"

CUSTOMER_RE = re.compile(r"\b[cC]\s?-?\s?(\d+)\b")
PRODUCT_RE = re.compile(r"\b[pP]\s?-?\s?(\d+)\b")
STORE_RE = re.compile(r"\bstores?\b|\boutlet\b|\bbranch\b|\blocation\b|\bshop\b", re.I)
STORE_ID_RE = re.compile(r"\b[sS]\s?-?\s?(\d{2,})\b")
TOP_N_RE = re.compile(r"\btop\s+(\d{1,3})\b", re.I)
LAST_DAYS_RE = re.compile(r"\b(?:last|past)\s+(\d{1,4})\s+days?\b", re.I)
PAST_MONTH_RE = re.compile(r"\bpast\s+month\b", re.I)
PAST_YEAR_RE = re.compile(r"\bpast\s+year\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
MONTH_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\b",
    re.I,
)

CUSTOMER_WORDS = ("customer", "client", "buyer", "shopper", "account")
DISCOUNT_WORDS = ("discount", "markdown", "promo", "% off", "percent off")
SPEND_WORDS = ("spent", "spend", "spending", "total", "how much", "worth")
HISTORY_WORDS = ("history", "purchased", "purchase", "bought", "buy", "orders?", "transactions?")
TOP_WORDS = ("top", "best", "popular", "highest", "biggest", "leading")
METRIC_WORDS = (
    "revenue", "sales", "turnover", "overview", "summary", "metrics",
    "kpi", "business", "overall", "total", "average basket", "basket",
)
HELP_WORDS = ("help", "what can you", "examples?", "how do i", "how to", "capabilit")


@dataclass
class ParsedQuery:
    intent: str
    customer_id: str | None = None
    product_id: str | None = None
    store_id: str | None = None
    top_n: int = 5
    since: str | None = None
    window_label: str | None = None
    raw: str = ""
    mentions_customer: bool = False
    mentions_product: bool = False


def _contains(text: str, words: tuple[str, ...]) -> bool:
    for w in words:
        if w.endswith("?"):  # e.g. "orders?" matches "order" or "orders"
            if re.search(rf"\b{w[:-1]}s?\b", text, re.I):
                return True
        elif w.isalnum():
            if re.search(rf"\b{w}\b", text, re.I):
                return True
        elif w.lower() in text.lower():
            return True
    return False


def parse_time_window(text: str, today: dt.date | None = None) -> tuple[str | None, str | None]:
    """Return (since_iso_date, human_label) for relative windows in ``text``."""
    today = today or dt.date.today()
    lowered = text.lower()
    m = LAST_DAYS_RE.search(text)
    if m:
        days = max(1, int(m.group(1)))
        since = today - dt.timedelta(days=days)
        return since.isoformat(), f"the last {days} days"
    if PAST_MONTH_RE.search(text):
        since = today - dt.timedelta(days=30)
        return since.isoformat(), "the past month"
    if PAST_YEAR_RE.search(text):
        since = today - dt.timedelta(days=365)
        return since.isoformat(), "the past year"
    m = MONTH_RE.search(lowered)
    if m:
        month = MONTHS[m.group(1)]
        year_match = YEAR_RE.search(text)
        year = int(year_match.group(1)) if year_match else today.year
        # Roll back a year when the month is still in the future.
        if year == today.year and month > today.month:
            year -= 1
        return dt.date(year, month, 1).isoformat(), f"{m.group(1).capitalize()} {year}"
    m = YEAR_RE.search(text)
    if m:
        return f"{m.group(1)}-01-01", f"{m.group(1)}"
    return None, None


def parse_query(text: str, today: dt.date | None = None) -> ParsedQuery:
    """Classify intent and extract entities from a natural language query."""
    raw = text or ""
    lowered = raw.strip().lower()

    customer_id = None
    m = CUSTOMER_RE.search(raw)
    if m:
        customer_id = f"C{m.group(1)}"
    product_id = None
    m = PRODUCT_RE.search(raw)
    if m:
        product_id = f"P{m.group(1)}"
    store_id = None
    m = STORE_ID_RE.search(raw)
    if m:
        store_id = f"S{m.group(1).zfill(2)}"

    top_n = 5
    m = TOP_N_RE.search(raw)
    if m:
        top_n = max(1, min(50, int(m.group(1))))

    # Scrub extracted IDs before time-window parsing so a year-like number
    # inside an ID (e.g. product P2024) is not mistaken for a year filter.
    scrubbed = raw
    for rx in (CUSTOMER_RE, PRODUCT_RE, STORE_ID_RE, TOP_N_RE):
        scrubbed = rx.sub(" ", scrubbed)
    since, window_label = parse_time_window(scrubbed, today)

    pq = ParsedQuery(
        intent=UNKNOWN,
        customer_id=customer_id,
        product_id=product_id,
        store_id=store_id,
        top_n=top_n,
        since=since,
        window_label=window_label,
        raw=raw.strip(),
        mentions_customer=_contains(lowered, CUSTOMER_WORDS),
        mentions_product=("product" in lowered or "item" in lowered or "sku" in lowered),
    )

    if not lowered or _contains(lowered, ("hello", "hi", "hey")) and len(lowered.split()) <= 2:
        pq.intent = HELP
        return pq
    if _contains(lowered, HELP_WORDS):
        pq.intent = HELP
        return pq

    has_customer = customer_id is not None
    has_product = product_id is not None
    has_top = _contains(lowered, TOP_WORDS) or TOP_N_RE.search(raw) is not None
    has_store_word = STORE_RE.search(raw) is not None
    has_discount = _contains(lowered, DISCOUNT_WORDS)
    has_spend = _contains(lowered, SPEND_WORDS)
    has_history = _contains(lowered, HISTORY_WORDS)
    has_metric = _contains(lowered, METRIC_WORDS)

    # Both a customer and a product -> the intersection question.
    if has_customer and has_product:
        pq.intent = CUSTOMER_PRODUCT
        return pq

    if has_customer:
        if has_spend and not has_history:
            pq.intent = CUSTOMER_TOTAL
        else:
            pq.intent = CUSTOMER_HISTORY
        return pq

    if has_product:
        if has_discount:
            pq.intent = PRODUCT_DISCOUNT
        elif "sell" in lowered or "sold" in lowered or has_store_word:
            pq.intent = PRODUCT_STORES
        else:
            pq.intent = PRODUCT_SUMMARY
        return pq

    if has_top:
        if "product" in lowered or "item" in lowered or "categor" in lowered:
            pq.intent = TOP_PRODUCTS
        elif "customer" in lowered or "client" in lowered or "buyer" in lowered:
            pq.intent = TOP_CUSTOMERS
        elif has_store_word:
            pq.intent = STORE_METRICS
        else:
            pq.intent = TOP_PRODUCTS
        return pq

    if has_store_word or store_id is not None:
        pq.intent = STORE_METRICS
        return pq

    if has_metric or "how many" in lowered or since is not None:
        pq.intent = BUSINESS_OVERVIEW
        return pq

    pq.intent = UNKNOWN
    return pq


def missing_entity_hint(pq: ParsedQuery) -> str | None:
    """Explain a missing ID when the user clearly meant one, else None."""
    low = pq.raw.lower()
    if pq.intent in (CUSTOMER_HISTORY, CUSTOMER_TOTAL, CUSTOMER_PRODUCT):
        return None
    if _contains(low, CUSTOMER_WORDS) and pq.customer_id is None:
        return (
            "I can look that up — which customer do you mean? "
            "Please include a customer ID like C10001."
        )
    if pq.mentions_product and pq.product_id is None and pq.intent == UNKNOWN:
        return (
            "I can look that up — which product do you mean? "
            "Please include a product ID like P1001."
        )
    return None
