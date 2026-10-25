"""M5: ingestion and scheduling (docs/plan.md). Polls run against a fake web serving the saved
fixtures; database tests run inside the test transaction (rolled back)."""

import asyncio
import os
import random
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from sabq.catalog import load_catalog, read_catalog
from sabq.cli import DEFAULT_CATALOG, DEFAULT_FIXTURES
from sabq.db.models import Article, ArticleVersion, ArticleWilaya, FetchRun, Source, Wilaya
from sabq.fetch import Fetcher
from sabq.ingest import store
from sabq.ingest.poller import Database, Job, Outcome, poll
from sabq.ingest.scheduler import Scheduler, load_jobs
from sabq.settings import Settings

T0 = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
FEED = "https://www.djelfainfo.dz/ar/rss.php"
ROBOTS = "https://www.djelfainfo.dz/robots.txt"
FIX = DEFAULT_FIXTURES / "djelfainfo-ar"


class FakeClock:
    t = 0.0

    def monotonic(self):
        return self.t

    def now(self):
        return T0

    async def sleep(self, seconds):
        self.t += seconds


class Web:
    """Fake sites: url -> (status, body, headers). Unknown URLs answer 404."""

    def __init__(self):
        self.pages = {ROBOTS: (200, (FIX / "robots.txt").read_bytes(), {})}
        self.requests: list[str] = []

    def set(self, url, body=b"", status=200, headers=None):
        self.pages[url] = (status, body, headers or {})

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(str(request.url))
        status, body, headers = self.pages.get(str(request.url), (404, b"", {}))
        return httpx2.Response(status, content=body, headers=headers)


@pytest.fixture
def web():
    return Web()


@pytest.fixture
def fetcher(web):
    return Fetcher(
        Settings(),
        transport=httpx2.MockTransport(web.handler),
        clock=FakeClock(),
        rng=random.Random(0),
    )


@pytest.fixture
def database(connection):
    factory = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    return Database(factory)


@pytest.fixture
def job(session) -> Job:
    entries = [e for e in read_catalog(DEFAULT_CATALOG) if e.slug == "djelfainfo-ar"]
    load_catalog(session, entries, "test")
    session.flush()
    return next(j for j in load_jobs(session) if j.slug == "djelfainfo-ar")


@pytest.fixture
def announced(monkeypatch):
    """NOTIFY calls made by store_items (the test transaction never commits, so none arrive)."""
    calls = []
    real = store.notify

    def spy(session, source_id, article_ids):
        calls.append(list(article_ids))
        real(session, source_id, article_ids)

    monkeypatch.setattr(store, "notify", spy)
    return calls


def listing(*, extra_item: str = "", retitle: str | None = None) -> bytes:
    xml = (FIX / "listing_1.xml").read_text(encoding="utf-8")
    if retitle:
        xml = xml.replace(
            "<title>رئيس الجمهورية يجري حركة جزئية في سلك الولاة</title>",
            f"<title>{retitle}</title>",
            1,
        )
    return xml.replace("<item>", extra_item + "<item>", 1).encode()


NEW_ITEM = (
    "<item><title>خبر جديد من الجلفة</title>"
    "<link>https://www.djelfainfo.dz/ar/news/djelfa/152499.html</link>"
    "<description>خبر جديد من الجلفة</description>"
    "<pubDate>2026-10-21T18:10:00+00:00</pubDate></item>"
)


def run_poll(job, fetcher, database, when):
    return asyncio.run(poll(job, fetcher, database, Settings(), now=lambda: when))


pytestmark_db = pytest.mark.db


# --- polls -----------------------------------------------------------------------------------


@pytestmark_db
def test_first_poll_is_baseline_then_new_articles_are_announced(
    session, web, fetcher, database, job, announced
):
    web.set(FEED, listing())
    first = run_poll(job, fetcher, database, T0)
    assert (first.status, first.seen, first.baseline, first.new) == ("ok", 10, 10, 0)
    assert not any(url.endswith(".html") for url in web.requests)  # no pages for a baseline
    assert announced == []

    articles = session.scalars(select(Article).where(Article.source_id == job.source_id)).all()
    assert len(articles) == 10 and all(a.baseline for a in articles)
    assert all(a.detection_delay_s is None for a in articles)
    codes = session.scalars(
        select(Wilaya.code).join(ArticleWilaya).where(ArticleWilaya.article_id == articles[0].id)
    ).all()
    assert codes == ["17"]

    # 15 minutes later one article appears; its page gives the lead the feed lacks
    web.set(FEED, listing(extra_item=NEW_ITEM))
    page = (FIX / "article_152481.html").read_bytes()
    web.set("https://www.djelfainfo.dz/ar/news/djelfa/152499.html", page)
    second = run_poll(job, fetcher, database, T0 + timedelta(minutes=15))
    assert (second.status, second.seen, second.new, second.baseline) == ("ok", 11, 1, 0)
    new = session.scalar(select(Article).where(Article.external_id == "152499"))
    assert not new.baseline
    assert new.lead.startswith("الرئيس تبون يجري حركة جزئية")  # og:description of that page
    assert new.detection_delay_s == pytest.approx(5 * 60)  # 18:10 published, 18:15 first seen
    assert announced == [[new.id]]
    assert [u for u in web.requests if u.endswith(".html")] == [
        "https://www.djelfainfo.dz/ar/news/djelfa/152499.html"
    ]

    # same listing again: nothing new, and the page lead is not lost (no version churn)
    third = run_poll(job, fetcher, database, T0 + timedelta(minutes=30))
    assert (third.new, third.updated) == (0, 0)
    session.expire_all()
    assert session.get(Article, new.id).version == 1
    runs = session.scalar(select(func.count()).where(FetchRun.source_id == job.source_id))
    assert runs == 3


@pytestmark_db
def test_changed_title_is_a_new_version(session, web, fetcher, database, job):
    web.set(FEED, listing())
    run_poll(job, fetcher, database, T0)
    web.set(FEED, listing(retitle="رئيس الجمهورية يجري حركة في سلك الولاة"))
    outcome = run_poll(job, fetcher, database, T0 + timedelta(minutes=15))
    assert (outcome.updated, outcome.new) == (1, 0)
    article = session.scalar(select(Article).where(Article.external_id == "152481"))
    session.refresh(article)
    assert (article.version, article.title) == (2, "رئيس الجمهورية يجري حركة في سلك الولاة")
    versions = session.scalars(
        select(ArticleVersion.version).where(ArticleVersion.article_id == article.id)
    ).all()
    assert sorted(versions) == [1, 2]


@pytestmark_db
def test_same_article_in_two_polls_is_stored_once(session, web, fetcher, database, job):
    web.set(FEED, listing())
    for minutes in (0, 15, 30, 45):
        run_poll(job, fetcher, database, T0 + timedelta(minutes=minutes))
    count = session.scalar(select(func.count()).where(Article.source_id == job.source_id))
    assert count == 10


@pytest.mark.parametrize(
    ("setup", "status", "error"),
    [
        (
            lambda web: web.set(ROBOTS, b"User-agent: *\nDisallow: /ar/"),
            "blocked_by_robots",
            "robots.txt",
        ),
        (lambda web: web.set(FEED, b"<html>maintenance</html>"), "broken", "not a readable feed"),
        (lambda web: web.set(FEED, status=404), "unreachable", "HTTP 404"),
        (
            lambda web: web.set(FEED, b'<?xml version="1.0"?><rss><channel></channel></rss>'),
            "empty",
            None,
        ),
    ],
)
@pytestmark_db
def test_source_status_after_a_poll(session, web, fetcher, database, job, setup, status, error):
    setup(web)
    outcome = run_poll(job, fetcher, database, T0)
    assert outcome.status == status
    session.expire_all()
    assert session.get(Source, job.source_id).status == status
    run = session.scalar(select(FetchRun).where(FetchRun.source_id == job.source_id))
    if error:
        assert error in run.error
    else:
        assert run.error is None


@pytestmark_db
def test_backing_off_host_records_nothing(session, web, fetcher, database, job):
    web.set(FEED, status=503)
    assert run_poll(job, fetcher, database, T0).status == "unreachable"
    skipped = run_poll(job, fetcher, database, T0 + timedelta(seconds=10))
    assert skipped.status is None and skipped.retry_in > 0
    runs = session.scalar(select(func.count()).where(FetchRun.source_id == job.source_id))
    assert runs == 1


@pytestmark_db
def test_baseline_after_a_long_gap(session, job):
    gap = timedelta(hours=24)
    assert store.is_baseline(session, job.source_id, T0, gap)  # never polled
    session.add(
        FetchRun(source_id=job.source_id, started_at=T0 - timedelta(hours=1), error="timeout")
    )
    session.flush()
    assert store.is_baseline(session, job.source_id, T0, gap)  # failures don't count
    session.add(FetchRun(source_id=job.source_id, started_at=T0 - timedelta(hours=2)))
    session.flush()
    assert not store.is_baseline(session, job.source_id, T0, gap)
    assert store.is_baseline(session, job.source_id, T0 + timedelta(days=2), gap)


@pytest.mark.db
def test_notify_reaches_a_listener():
    """Outside the test transaction: NOTIFY is delivered on commit to a LISTENing connection."""
    import json

    import psycopg

    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, autocommit=True) as listener, psycopg.connect(url) as writer:
        listener.execute(f"LISTEN {store.NOTIFY_CHANNEL}")
        writer.execute("SELECT pg_notify(%s, %s)", (store.NOTIFY_CHANNEL, json.dumps({"x": 1})))
        writer.commit()
        received = list(listener.notifies(timeout=5, stop_after=1))
    assert json.loads(received[0].payload) == {"x": 1}


# --- scheduler (no database: jobs and polls are stubs) -----------------------------------------


def make_job(source_id: int, interval: int = 600) -> Job:
    entry = next(e for e in read_catalog(DEFAULT_CATALOG) if e.slug == "djelfainfo-ar")
    return Job(source_id, f"src-{source_id}", "ar", "default", interval, "ok", entry)


class StubDatabase:
    def __init__(self, jobs):
        self.jobs = jobs

    async def run(self, fn, *args, **kwargs):
        assert fn is load_jobs
        return self.jobs


def test_scheduler_staggers_jitters_and_respects_outcomes(monkeypatch):
    outcomes = {1: Outcome("ok"), 2: Outcome(None, retry_in=300.0), 3: Outcome("blocked_by_robots")}
    polled = []

    async def fake_poll(job, fetcher, db, settings):
        polled.append(job.source_id)
        return outcomes[job.source_id]

    monkeypatch.setattr("sabq.ingest.scheduler.poll", fake_poll)
    clock = FakeClock()
    jobs = [make_job(1), make_job(2), make_job(3)]
    scheduler = Scheduler(Settings(), None, StubDatabase(jobs), clock=clock, rng=random.Random(3))

    async def scenario():
        await scheduler.tick()  # all get a first due time within the 10 s stagger
        assert polled == []
        clock.t += 10
        await scheduler.tick()
        await scheduler.drain()
        return dict(scheduler.next_at)

    next_at = asyncio.run(scenario())
    assert sorted(polled) == [1, 2, 3]
    assert 480 <= next_at[1] - clock.t <= 720  # 600 s ± 20 %
    assert next_at[2] - clock.t == pytest.approx(300)  # backoff
    assert next_at[3] - clock.t >= 86400  # blocked: wait for robots.txt to expire


def test_scheduler_never_runs_one_source_twice_and_drops_disabled(monkeypatch):
    gate = asyncio.Event()
    calls = []

    async def slow_poll(job, fetcher, db, settings):
        calls.append(job.source_id)
        await gate.wait()
        return Outcome("ok")

    monkeypatch.setattr("sabq.ingest.scheduler.poll", slow_poll)
    clock = FakeClock()
    db = StubDatabase([make_job(1, interval=60)])
    scheduler = Scheduler(Settings(), None, db, clock=clock, rng=random.Random(0))

    async def scenario():
        clock.t += 100
        await scheduler.tick()
        await scheduler.tick()  # sets the first due time; then due on the next ticks
        clock.t += 100
        await scheduler.tick()
        await asyncio.sleep(0)
        clock.t += 100
        await scheduler.tick()  # still running: not started again
        gate.set()
        await scheduler.drain()
        db.jobs = []
        await scheduler.tick()
        return scheduler.next_at

    next_at = asyncio.run(scenario())
    assert calls == [1]
    assert next_at == {}
