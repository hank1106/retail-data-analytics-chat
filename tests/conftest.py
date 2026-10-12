"""Shared fixtures: temp SQLite DB seeded from the bundled sample CSV."""

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = ROOT / "data" / "sample_transactions.csv"


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    """Force template answers so tests never need network or API keys."""
    monkeypatch.setenv("LLM_PROVIDER", "off")


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(db.SCHEMA)
    import pandas as pd

    df = pd.read_csv(SAMPLE_CSV).rename(columns=db.CSV_RENAME)
    df["customer_id"] = df["customer_id"].astype(str).str.strip()
    df["product_id"] = df["product_id"].astype(str).str.strip().str.upper()
    df[db.COLUMNS].to_sql("transactions", connection, if_exists="append", index=False)
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    from app import main

    test_db = tmp_path / "test.db"
    db.init_db(test_db, SAMPLE_CSV)
    monkeypatch.setattr(main, "DB_PATH", test_db)
    return TestClient(main.app)
