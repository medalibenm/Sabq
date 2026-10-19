import asyncio
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from sabq import __version__
from sabq.logs import JsonFormatter
from sabq.settings import Settings, get_settings
from sabq.worker import run


def test_user_agent_without_contact_url():
    assert Settings(sabqbot_contact_url="").user_agent == f"SabqBot/{__version__}"


def test_user_agent_with_contact_url():
    agent = Settings(sabqbot_contact_url="https://example.org/bot").user_agent
    assert agent == f"SabqBot/{__version__} (+https://example.org/bot)"


def test_json_log_keeps_arabic():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "وكالة الأنباء", None, None)
    entry = json.loads(JsonFormatter().format(record))
    assert entry["msg"] == "وكالة الأنباء"
    assert entry["level"] == "INFO"


def test_worker_heartbeat_and_clean_stop(tmp_path: Path):
    heartbeat = tmp_path / "heartbeat"
    settings = Settings(worker_heartbeat_file=str(heartbeat), worker_tick_seconds=0.01)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(run(settings, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())
    assert heartbeat.exists()


@pytest.mark.db
def test_health_ok_with_database():
    from sabq.app import app

    response = TestClient(app).get("/health.json")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "database": "ok"}


@pytest.mark.db
def test_migrations_up_and_down():
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    engine = create_engine(get_settings().database_url)

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()

    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        assert not conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()

    command.upgrade(cfg, "head")
    engine.dispose()
