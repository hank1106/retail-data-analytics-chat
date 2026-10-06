"""Shared pytest fixtures: deterministic temp database and app client."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retail_chat.api import create_app  # noqa: E402
from retail_chat.config import Settings  # noqa: E402
from retail_chat.db import connect, init_schema  # noqa: E402
from retail_chat.data_loader import load_csv  # noqa: E402
from retail_chat.llm import Responder, TemplateProvider  # noqa: E402
from retail_chat.repository import RetailRepository  # noqa: E402
from retail_chat.seed import generate_rows, write_seed_csv  # noqa: E402

N_ROWS = 300
SEED = 7


@pytest.fixture()
def seed_rows():
    return generate_rows(N_ROWS, SEED)


@pytest.fixture()
def db_path(tmp_path):
    csv_path = write_seed_csv(tmp_path / "seed.csv", n_rows=N_ROWS, seed=SEED)
    db = tmp_path / "test.db"
    conn = connect(db)
    try:
        init_schema(conn)
        count = load_csv(csv_path, conn)
        assert count == N_ROWS
    finally:
        conn.close()
    return db


@pytest.fixture()
def repo(db_path):
    conn = connect(db_path)
    try:
        yield RetailRepository(conn)
    finally:
        conn.close()


@pytest.fixture()
def responder():
    return Responder(primary=TemplateProvider())


@pytest.fixture()
def client(db_path):
    settings = Settings(llm_provider="template", database_path=str(db_path))
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as c:
        yield c
