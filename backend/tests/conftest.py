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
def connection(migrated):
    """A connection inside a transaction that is rolled back after the test."""
    from sabq.db.session import get_sync_engine

    connection = get_sync_engine().connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _empty_tables() -> None:
    from sqlalchemy import text

    from sabq.db.session import get_sync_engine

    with get_sync_engine().begin() as conn:  # keeps the seeded wilayas
        conn.execute(text("TRUNCATE organisations, sources, audit_events RESTART IDENTITY CASCADE"))


@pytest.fixture
def committed(migrated):
    """For tests through the HTTP app, whose own connections can't see the test transaction:
    data is committed for real, and the tables are emptied before and after."""
    from sqlalchemy.orm import Session

    from sabq.db.session import get_sync_engine

    _empty_tables()
    with Session(get_sync_engine(), expire_on_commit=False) as db:
        yield db
    _empty_tables()


@pytest.fixture
def client(committed, monkeypatch):
    """The app over HTTPS (so Secure cookies are sent), with emails captured in client.outbox."""
    from fastapi.testclient import TestClient

    from sabq.api import auth as auth_api
    from sabq.auth import mail
    from sabq.db import session as db_session
    from sabq.settings import get_settings

    outbox = []
    monkeypatch.setattr(mail, "send", lambda settings, message: outbox.append(message))
    for cached in (db_session.get_engine, db_session.get_sessionmaker, auth_api.limiter):
        cached.cache_clear()  # async engine and limiter bound to this test's event loop
    get_settings.cache_clear()
    from sabq.app import app

    with TestClient(app, base_url="https://testserver") as test_client:
        test_client.outbox = outbox
        yield test_client
    for cached in (db_session.get_engine, db_session.get_sessionmaker, auth_api.limiter):
        cached.cache_clear()


@pytest.fixture
def session(connection):
    """A session in the test transaction (its commits become savepoints)."""
    from sqlalchemy.orm import Session

    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
