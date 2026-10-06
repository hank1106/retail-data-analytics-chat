"""Data loading: Kaggle CSV (or any CSV) -> SQLite, plus a seed fallback.

The Kaggle "Retail Transaction Dataset" has no frozen schema guarantee, so
headers are normalized (lowercased, stripped of spaces/underscores/dashes)
and matched against known aliases for each canonical column. Unrecognized
columns are ignored; missing optional columns stay NULL. ``total_amount``
is derived from quantity x price x (1 - discount) when absent.

Usage::

    python -m retail_chat.data_loader --seed            # seed demo database
    python -m retail_chat.data_loader --csv data/my.csv # load your own CSV
    python -m retail_chat.data_loader --kaggle          # download from Kaggle
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .db import connect, init_schema, row_count
from .seed import write_seed_csv

CANONICAL_COLUMNS = [
    "transaction_id", "customer_id", "product_id", "store_id", "quantity",
    "unit_price", "discount", "total_amount", "transaction_date",
    "payment_method", "product_category",
]

# Normalized header -> canonical column. Normalization = lowercase and drop
# spaces, underscores and dashes.
COLUMN_ALIASES = {
    "transactionid": "transaction_id",
    "tid": "transaction_id",
    "invoiceno": "transaction_id",
    "invoice": "transaction_id",
    "billno": "transaction_id",
    "orderid": "transaction_id",
    "customerid": "customer_id",
    "customer": "customer_id",
    "custid": "customer_id",
    "clientid": "customer_id",
    "productid": "product_id",
    "product": "product_id",
    "itemid": "product_id",
    "item": "product_id",
    "sku": "product_id",
    "stockcode": "product_id",
    "storeid": "store_id",
    "store": "store_id",
    "outlet": "store_id",
    "branch": "store_id",
    "location": "store_id",
    "storelocation": "store_id",
    "shop": "store_id",
    "quantity": "quantity",
    "qty": "quantity",
    "units": "quantity",
    "unitprice": "unit_price",
    "price": "unit_price",
    "rate": "unit_price",
    "unitcost": "unit_price",
    "discount": "discount",
    "disc": "discount",
    "discountpct": "discount",
    "discountpercent": "discount",
    "discountrate": "discount",
    "totalamount": "total_amount",
    "total": "total_amount",
    "amount": "total_amount",
    "sales": "total_amount",
    "revenue": "total_amount",
    "netamount": "total_amount",
    "grandtotal": "total_amount",
    "transactiondate": "transaction_date",
    "date": "transaction_date",
    "invoicedate": "transaction_date",
    "timestamp": "transaction_date",
    "datetime": "transaction_date",
    "day": "transaction_date",
    "paymentmethod": "payment_method",
    "payment": "payment_method",
    "paymethod": "payment_method",
    "productcategory": "product_category",
    "category": "product_category",
    "department": "product_category",
    "type": "product_category",
}


def normalize_header(header: str) -> str:
    return (
        header.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    )


def map_headers(headers: list[str]) -> dict[int, str | None]:
    """Map each CSV column index to a canonical column (or None to skip)."""
    mapping: dict[int, str | None] = {}
    for i, header in enumerate(headers):
        norm = normalize_header(header)
        if norm in CANONICAL_COLUMNS:
            mapping[i] = norm
        else:
            mapping[i] = COLUMN_ALIASES.get(norm)
    return mapping


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        cleaned = str(value).strip().replace("$", "").replace(",", "")
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _to_discount(value: float | None) -> float | None:
    # Accept both fractions (0.15) and percents (15).
    if value is None:
        return None
    if value > 1:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def load_csv(csv_path: str | Path, conn: sqlite3.Connection) -> int:
    """Load a CSV file into the ``transactions`` table. Returns row count."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError(f"CSV file is empty: {csv_path}")
        mapping = map_headers(headers)
        if "customer_id" not in mapping.values():
            raise ValueError(
                "Could not find a customer ID column in "
                f"{csv_path} (headers: {headers}). Expected something like "
                "'CustomerID'."
            )
        if "product_id" not in mapping.values():
            raise ValueError(
                "Could not find a product ID column in "
                f"{csv_path} (headers: {headers}). Expected something like "
                "'ProductID'."
            )
        rows: list[tuple] = []
        for line in reader:
            if not line or all(not cell.strip() for cell in line):
                continue
            record: dict[str, object] = {}
            for i, cell in enumerate(line):
                canonical = mapping.get(i)
                if canonical:
                    record[canonical] = cell.strip()
            qty = _to_int(record.get("quantity"))  # type: ignore[arg-type]
            price = _to_float(record.get("unit_price"))  # type: ignore[arg-type]
            discount = _to_discount(_to_float(record.get("discount")))  # type: ignore[arg-type]
            total = _to_float(record.get("total_amount"))  # type: ignore[arg-type]
            if total is None and qty is not None and price is not None:
                total = round(qty * price * (1 - (discount or 0.0)), 2)
            rows.append(
                (
                    record.get("transaction_id") or None,
                    record.get("customer_id"),
                    record.get("product_id"),
                    record.get("store_id") or None,
                    qty,
                    price,
                    discount,
                    total,
                    record.get("transaction_date") or None,
                    record.get("payment_method") or None,
                    record.get("product_category") or None,
                )
            )
    conn.execute("DELETE FROM transactions")
    conn.executemany(
        "INSERT INTO transactions (transaction_id, customer_id, product_id,"
        " store_id, quantity, unit_price, discount, total_amount,"
        " transaction_date, payment_method, product_category)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def find_dataset_csv(data_dir: str | Path) -> Path | None:
    """Return the first ``*.csv`` in ``data_dir``, if any."""
    csvs = sorted(Path(data_dir).glob("*.csv"))
    return csvs[0] if csvs else None


def download_from_kaggle(slug: str, dest_dir: str | Path) -> Path:
    """Download the Kaggle dataset into ``dest_dir``.

    Requires the ``kaggle`` package (``pip install kaggle``) and Kaggle API
    credentials (``~/.kaggle/kaggle.json`` or ``KAGGLE_USERNAME`` /
    ``KAGGLE_KEY``). Returns the downloaded CSV path.
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:
        raise RuntimeError(
            "The 'kaggle' package is not installed. Install it with "
            "'pip install kaggle' and configure credentials, or download "
            f"'https://www.kaggle.com/datasets/{slug}/data' manually into data/."
        ) from exc
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(slug, path=str(dest), unzip=True)
    csv_path = find_dataset_csv(dest)
    if csv_path is None:
        raise RuntimeError(
            f"Kaggle download finished but no CSV found in {dest}. "
            "Check the dataset contents."
        )
    return csv_path


def ensure_database(
    db_path: str | Path | None = None,
    csv_path: str | Path | None = None,
    seed_rows: int = 1500,
    seed: int = 42,
) -> Path:
    """Make sure a populated SQLite database exists; return its path."""
    settings = Settings.from_env()
    db = Path(db_path) if db_path else settings.resolve_db_path()
    conn = connect(db)
    try:
        init_schema(conn)
        if row_count(conn) > 0:
            return db
        csv = (
            Path(csv_path)
            if csv_path
            else (Path(settings.data_csv) if settings.data_csv else None)
        )
        if csv is None:
            csv = find_dataset_csv(PROJECT_ROOT / "data")
        if csv is not None:
            n = load_csv(csv, conn)
            print(f"Loaded {n} rows from {csv} into {db}")
        else:
            seed_csv = PROJECT_ROOT / "data" / "seed_transactions.csv"
            if not seed_csv.exists():
                write_seed_csv(seed_csv, n_rows=seed_rows, seed=seed)
                print(f"Generated seed data: {seed_csv}")
            n = load_csv(seed_csv, conn)
            print(f"Loaded {n} seed rows into {db}")
        return db
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load retail data into SQLite.")
    parser.add_argument("--db", default=None, help="SQLite path (default: from env)")
    parser.add_argument("--csv", default=None, help="CSV file to load")
    parser.add_argument("--seed", action="store_true", help="Force seed-data reload")
    parser.add_argument("--seed-rows", type=int, default=1500)
    parser.add_argument("--kaggle", action="store_true", help="Download from Kaggle")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.kaggle:
        csv_path = download_from_kaggle(settings.kaggle_dataset, PROJECT_ROOT / "data")
        print(f"Downloaded: {csv_path}")
    if args.seed:
        seed_csv = PROJECT_ROOT / "data" / "seed_transactions.csv"
        write_seed_csv(seed_csv, n_rows=args.seed_rows)
        db = ensure_database(args.db, seed_csv)
    else:
        db = ensure_database(args.db, args.csv)
    print(f"Database ready: {db}")


if __name__ == "__main__":
    main()
