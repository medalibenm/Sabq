import asyncio
import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # psycopg's async driver needs a selector loop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(config, items):
    """Database tests run only when DATABASE_URL is set (CI, or `docker compose` locally)."""
    if os.environ.get("DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="DATABASE_URL not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def alembic_cfg():
    from alembic.config import Config

    return Config(str(BACKEND / "alembic.ini"))


@pytest.fixture(scope="session")
def migrated(alembic_cfg):
    """Database at the latest migration (once per test run)."""
    from alembic import command

    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def session(migrated):
    """A session inside a transaction that is rolled back after the test."""
    from sqlalchemy.orm import Session

    from sabq.db.session import get_sync_engine

    connection = get_sync_engine().connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
