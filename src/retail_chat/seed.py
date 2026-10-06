"""Deterministic synthetic seed data.

Used when no real dataset CSV is available, so the system (and its tests)
runs out of the box. Generation is fully deterministic for a given
``(n_rows, seed)`` pair, which lets the test suite recompute expected
aggregates independently in plain Python.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path

CUSTOMER_IDS = [f"C{10001 + i}" for i in range(60)]

PRODUCTS = [
    (f"P{1001 + i}", cat, price)
    for i, (cat, price) in enumerate(
        [
            ("Groceries", 4.50), ("Groceries", 2.99), ("Groceries", 7.25),
            ("Electronics", 199.99), ("Electronics", 49.95), ("Electronics", 129.00),
            ("Clothing", 29.99), ("Clothing", 59.50), ("Clothing", 19.95),
            ("Home", 89.00), ("Home", 34.75), ("Home", 12.40),
            ("Beauty", 15.99), ("Beauty", 27.50), ("Beauty", 9.99),
            ("Sports", 79.99), ("Sports", 45.00), ("Sports", 22.30),
            ("Toys", 24.99), ("Toys", 39.99), ("Toys", 14.50),
            ("Books", 18.00), ("Books", 25.00), ("Books", 11.99),
            ("Groceries", 5.75), ("Electronics", 249.00), ("Clothing", 44.99),
            ("Home", 59.99), ("Beauty", 32.00), ("Sports", 99.95),
            ("Toys", 49.99), ("Books", 21.50), ("Groceries", 8.99),
            ("Electronics", 79.50), ("Clothing", 69.00), ("Home", 149.00),
            ("Beauty", 19.50), ("Sports", 129.99), ("Toys", 29.99),
            ("Books", 16.75),
        ]
    )
]

STORE_IDS = ["S01", "S02", "S03", "S04", "S05"]
PAYMENT_METHODS = ["cash", "card", "mobile"]
DISCOUNTS = [0.0, 0.0, 0.0, 0.05, 0.10, 0.15, 0.20]

START_DATE = dt.date(2024, 1, 1)
END_DATE = dt.date(2024, 12, 31)

HEADERS = [
    "transaction_id", "customer_id", "product_id", "store_id", "quantity",
    "unit_price", "discount", "total_amount", "transaction_date",
    "payment_method", "product_category",
]


def generate_rows(n_rows: int = 1500, seed: int = 42) -> list[dict]:
    """Generate ``n_rows`` deterministic transaction dicts."""
    rng = random.Random(seed)
    span = (END_DATE - START_DATE).days
    rows: list[dict] = []
    for i in range(n_rows):
        customer_id = rng.choice(CUSTOMER_IDS)
        product_id, category, base_price = rng.choice(PRODUCTS)
        store_id = rng.choice(STORE_IDS)
        quantity = rng.randint(1, 5)
        unit_price = round(base_price * rng.uniform(0.9, 1.1), 2)
        discount = rng.choice(DISCOUNTS)
        total = round(quantity * unit_price * (1 - discount), 2)
        day = START_DATE + dt.timedelta(days=rng.randint(0, span))
        rows.append(
            {
                "transaction_id": f"T{100001 + i}",
                "customer_id": customer_id,
                "product_id": product_id,
                "store_id": store_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "discount": discount,
                "total_amount": total,
                "transaction_date": day.isoformat(),
                "payment_method": rng.choice(PAYMENT_METHODS),
                "product_category": category,
            }
        )
    return rows


def write_seed_csv(path: str | Path, n_rows: int = 1500, seed: int = 42) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(generate_rows(n_rows, seed))
    return path
