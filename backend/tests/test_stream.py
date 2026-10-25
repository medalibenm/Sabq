"""M6: live updates by SSE. The stream sends only what the user's organisation may see."""

import asyncio
import json
import os

import psycopg
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_webapp import world  # noqa: F401  (fixture)

from sabq.api import stream
from sabq.api.stream import Broadcaster, event_stream
from sabq.auth import service
from sabq.db.models import Organisation, User, UserSession
from sabq.ingest.store import NOTIFY_CHANNEL
from sabq.settings import Settings

pytestmark = pytest.mark.db
URL = os.environ.get("DATABASE_URL", "")


def org_and_token(db, slug: str, email: str) -> tuple[int, str]:
    org_id = db.scalar(select(Organisation.id).where(Organisation.slug == slug))
    user = db.scalar(select(User).where(User.email == email))
    token = service.start_session(db, Settings(), user)
    db.commit()
    return org_id, token


async def collect(events, count: int) -> list[str]:
    out = []
    async for event in events:
        out.append(event)
        if len(out) == count:
            break
    return out


def ids_of(events: list[str]) -> list[int]:
    return [int(e.split("\n", 1)[0].removeprefix("id: ")) for e in events if e.startswith("id:")]


async def never_disconnected() -> bool:
    return False


def scenario(fn):
    """Run with an async engine created in this test's event loop."""

    async def wrapper():
        engine = create_async_engine(URL)
        try:
            return await fn(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(wrapper())


def test_only_visible_articles_are_pushed(world):  # noqa: F811
    db, ids = world
    org_a, token = org_and_token(db, "org-a", "a@org-a.dz")

    async def run(factory):
        broadcaster = Broadcaster(URL)
        events = event_stream(broadcaster, org_a, token, None, never_disconnected, factory, 5)
        assert await anext(events) == "retry: 5000\n\n"
        broadcaster.publish([ids["batna-local"], ids["oran-local"], ids["batna-about-oran"]])
        (event,) = await collect(events, 1)
        await events.aclose()
        assert broadcaster.subscribers == set()  # unsubscribed on close
        return event

    event = scenario(run)
    assert ids_of([event]) == [ids["batna-local"]]
    data = json.loads(event.split("data: ", 1)[1])
    assert data["source"]["slug"] == "batna-src" and "body_text" not in data


def test_reconnect_replays_newer_visible_articles(world):  # noqa: F811
    db, ids = world
    org_a, token = org_and_token(db, "org-a", "a@org-a.dz")

    async def run(factory):
        events = event_stream(Broadcaster(URL), org_a, token, 0, never_disconnected, factory, 5)
        return await collect(events, 3)  # retry + 2 replayed

    replayed = scenario(run)
    assert ids_of(replayed) == sorted([ids["batna-local"], ids["batna-national"]])


def test_pings_reload_and_logout(world, monkeypatch):  # noqa: F811
    db, ids = world
    org_a, token = org_and_token(db, "org-a", "a@org-a.dz")
    monkeypatch.setattr(stream, "QUEUE_SIZE", 1)
    monkeypatch.setattr(stream, "SESSION_CHECK_EVERY", 2)

    async def run(factory):
        broadcaster = Broadcaster(URL)
        events = event_stream(broadcaster, org_a, token, None, never_disconnected, factory, 0.05)
        await anext(events)  # retry
        first = await anext(events)  # nothing happens: a ping
        broadcaster.publish([ids["batna-local"]])
        broadcaster.publish([ids["batna-local"]])  # queue of 1 is full: overflow
        overflow = await anext(events)
        db.execute(delete(UserSession))  # logged out elsewhere
        db.commit()
        rest = await collect(events, 5)
        return first, overflow, rest

    first, overflow, rest = scenario(run)
    assert first == ": ping\n\n"
    assert overflow.startswith("event: reload")
    assert rest[-1].startswith("event: logout")  # and the stream ended


def test_broadcaster_hears_notify():
    async def run(_factory):
        broadcaster = Broadcaster(URL)
        broadcaster.start()
        await asyncio.wait_for(broadcaster.listening.wait(), 10)
        subscriber = broadcaster.subscribe(1)

        def notify():
            with psycopg.connect(URL.replace("+psycopg", "")) as conn:
                payload = json.dumps({"source_id": 1, "article_ids": [41, 42]})
                conn.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, payload))

        await asyncio.to_thread(notify)
        received = await asyncio.wait_for(subscriber.queue.get(), 10)
        await broadcaster.stop()
        return received

    assert scenario(run) == [41, 42]


def test_stream_needs_login(client):
    assert client.get("/app/stream").status_code == 401
