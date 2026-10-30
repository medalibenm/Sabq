"""Live updates by Server-Sent Events (decision 2026-10-21): `GET /app/stream`.

The worker announces new articles with `NOTIFY sabq_new_articles {"source_id", "article_ids"}`
in the transaction that stores them. Each app process keeps one `LISTEN` connection
(`Broadcaster`) and hands every notification to the connected browsers' queues; each stream then
sends only the articles its organisation may see (the same access rule as every read).

    event: article        one new article (same shape as /app/articles items), id = article id
    : ping                every 15 s, keeps proxies from closing the connection
    event: reload         the browser fell behind (queue full): refetch /app/articles

A reconnecting browser sends `Last-Event-ID`; newer (non-baseline) articles are replayed first.
The session is re-checked every few minutes, so logging out also ends open streams.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated

import psycopg
from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from sabq.api.articles import filtered, to_out
from sabq.api.deps import LoggedIn
from sabq.auth.service import digest, now
from sabq.db.models import Article, UserSession
from sabq.db.session import get_sessionmaker
from sabq.ingest.store import NOTIFY_CHANNEL
from sabq.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/app", tags=["web app"])

PING_S = 15.0
SESSION_CHECK_EVERY = 20  # pings: about every 5 minutes
QUEUE_SIZE = 200
REPLAY_LIMIT = 100


@dataclass(eq=False)
class Subscriber:
    organisation_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    overflowed: bool = False


class Broadcaster:
    """One LISTEN connection per process, fanned out to subscribers; reconnects by itself."""

    def __init__(self, database_url: str):
        self.url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.subscribers: set[Subscriber] = set()
        self.listening = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def subscribe(self, organisation_id: int) -> Subscriber:
        subscriber = Subscriber(organisation_id)
        self.subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self.subscribers.discard(subscriber)

    def publish(self, article_ids: list[int]) -> None:
        for subscriber in list(self.subscribers):
            try:
                subscriber.queue.put_nowait(article_ids)
            except asyncio.QueueFull:
                subscriber.overflowed = True

    async def _listen(self) -> None:
        delay = 1.0
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(self.url, autocommit=True) as conn:
                    await conn.execute(f"LISTEN {NOTIFY_CHANNEL}")
                    self.listening.set()
                    delay = 1.0
                    async for notice in conn.notifies():
                        try:
                            ids = [int(i) for i in json.loads(notice.payload)["article_ids"]]
                        except (ValueError, KeyError, TypeError):
                            log.warning("ignored notification %r", notice.payload)
                            continue
                        self.publish(ids)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # database restart, network: try again
                self.listening.clear()
                log.warning("LISTEN connection lost (%s), retrying in %.0f s", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)


def sse(event: str, data: str, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {data}\n\n"


async def _visible_events(
    factory: async_sessionmaker, organisation_id: int, query_ids: list[int] | None, after: int
) -> list[str]:
    async with factory() as db:
        query = filtered(organisation_id).where(Article.baseline.is_(False))
        if query_ids is not None:
            query = query.where(Article.id.in_(query_ids))
        else:
            query = query.where(Article.id > after)
        rows = list(await db.scalars(query.order_by(Article.id).limit(REPLAY_LIMIT)))
        items = await to_out(db, rows, organisation_id=organisation_id)
        return [sse("article", item.model_dump_json(), item.id) for item in items]


async def _session_valid(factory: async_sessionmaker, token: str) -> bool:
    async with factory() as db:
        row = await db.get(UserSession, digest(token))
        return row is not None and row.expires_at > now()


async def event_stream(
    broadcaster: Broadcaster,
    organisation_id: int,
    session_token: str,
    last_event_id: int | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    factory: async_sessionmaker | None = None,
    ping_s: float = PING_S,
) -> AsyncIterator[str]:
    factory = factory or get_sessionmaker()
    subscriber = broadcaster.subscribe(organisation_id)
    try:
        yield "retry: 5000\n\n"
        if last_event_id is not None:
            for event in await _visible_events(factory, organisation_id, None, last_event_id):
                yield event
        pings = 0
        while not await is_disconnected():
            try:
                ids = await asyncio.wait_for(subscriber.queue.get(), timeout=ping_s)
            except TimeoutError:
                pings += 1
                if pings % SESSION_CHECK_EVERY == 0 and not await _session_valid(
                    factory, session_token
                ):
                    yield sse("logout", "{}")
                    return
                yield ": ping\n\n"
                continue
            if subscriber.overflowed:
                subscriber.overflowed = False
                while not subscriber.queue.empty():
                    subscriber.queue.get_nowait()
                yield sse("reload", "{}")
                continue
            for event in await _visible_events(factory, organisation_id, ids, 0):
                yield event
    finally:
        broadcaster.unsubscribe(subscriber)


@router.get("/stream", response_class=StreamingResponse)
async def stream(
    request: Request,
    viewer: LoggedIn,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """New articles as they are found (text/event-stream). See the module docs for events."""
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
    return StreamingResponse(
        event_stream(
            request.app.state.broadcaster,
            viewer.organisation.id,
            viewer.token,
            after,
            request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def make_broadcaster() -> Broadcaster:
    return Broadcaster(get_settings().database_url)
