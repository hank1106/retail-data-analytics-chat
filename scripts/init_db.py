"""Initialize the SQLite database from the Kaggle CSV or the bundled sample.

Usage:
    python scripts/init_db.py [--csv PATH] [--db PATH]

Default CSV resolution:
  1. --csv argument
  2. $RETAIL_CSV env var
  3. kagglehub cache for fahadrehman07/retail-transaction-dataset
  4. data/sample_transactions.csv (bundled, always works offline)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402


def resolve_csv(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.getenv("RETAIL_CSV")
    if env:
        return Path(env)
    try:
        import kagglehub  # type: ignore

        cached = Path(kagglehub.dataset_download("fahadrehman07/retail-transaction-dataset"))
        csvs = sorted(cached.glob("*.csv"))
        if csvs:
            return csvs[0]
    except Exception as exc:
        print(f"kagglehub download skipped ({exc}); falling back to sample CSV.")
    return ROOT / "data" / "sample_transactions.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load retail CSV into SQLite.")
    parser.add_argument("--csv", default=None, help="Path to Retail_Transaction_Dataset.csv")
    parser.add_argument("--db", default=None, help="Destination SQLite path")
    args = parser.parse_args()

    csv_path = resolve_csv(args.csv)
    db_path = Path(args.db or os.getenv("RETAIL_DB", ROOT / "data" / "retail.db"))
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    rows = db.init_db(db_path, csv_path)
    conn = db.connect(db_path)
    try:
        customers = db.get_customer_count(conn)
        products = db.get_known_product_ids(conn)
        revenue = db.get_business_metrics(conn)["total_revenue"]
    finally:
        conn.close()
    print(f"Loaded {rows} rows from {csv_path} into {db_path}")
    print(f"Customers: {customers} | Products: {products} | Revenue: ${revenue:,.2f}")


if __name__ == "__main__":
    main()
