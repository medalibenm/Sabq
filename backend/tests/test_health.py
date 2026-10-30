"""M7: source health and breakage (docs/plan.md)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_auth import login, make_user
from test_ingest import FakeClock, Web, run_poll

from sabq.catalog import load_catalog, read_catalog
from sabq.cli import DEFAULT_CATALOG
from sabq.db.models import Source
from sabq.fetch import Fetcher
from sabq.health import SourceHealth, rhythm, usual_quiet_period, warnings_for
from sabq.ingest.poller import Database
from sabq.ingest.scheduler import load_jobs
from sabq.ingest.store import record_run
from sabq.settings import Settings

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def health(**fields) -> SourceHealth:
    base = dict(
        slug="s",
        name="s",
        enabled=True,
        status="ok",
        status_since=None,
        access_method="rss",
        poll_interval_s=300,
    )
    return SourceHealth(**(base | fields))


# --- rules -----------------------------------------------------------------------------------


def test_usual_quiet_period_handles_bursty_and_regular_sources():
    # Awras-like: ~70 posts within 10 minutes, once a day, for a week
    bursty = [
        NOW - timedelta(days=d) + timedelta(seconds=8 * i) for d in range(7) for i in range(70)
    ]
    assert usual_quiet_period(bursty) == pytest.approx(86400 - 69 * 8, rel=0.01)
    hourly = [NOW - timedelta(hours=h) for h in range(48)]
    assert usual_quiet_period(hourly) == pytest.approx(3600)
    assert usual_quiet_period([NOW, NOW - timedelta(hours=1)]) is None  # not enough history


def test_silence_warning_uses_three_times_the_usual_quiet_period():
    daily = health(usual_quiet_s=86400, last_new_at=NOW - timedelta(days=2))
    assert warnings_for(daily, NOW) == []  # two days quiet is normal-ish for a daily source
    daily.last_new_at = NOW - timedelta(days=3, hours=1)
    assert warnings_for(daily, NOW)[0].startswith("silent: no new article for 3 days")
    learning = health(usual_quiet_s=None, last_new_at=NOW - timedelta(days=30))
    assert warnings_for(learning, NOW) == []


def test_failing_fewer_items_and_stale_warnings():
    found = warnings_for(
        health(
            failures_in_a_row=3,
            last_items_seen=4,
            usual_items_seen=30,
            last_success_at=NOW - timedelta(hours=7),
        ),
        NOW,
    )
    assert [w.split(":")[0] for w in found] == ["failing", "fewer items", "stale"]
    assert warnings_for(health(status="empty", last_items_seen=0, usual_items_seen=30), NOW) == []


def test_problems_sort_first():
    rows = [
        health(slug="a-ok"),
        health(slug="b-broken", status="broken"),
        health(slug="c-silent", warnings=["silent: ..."]),
        health(slug="d-empty", status="empty"),
        health(slug="e-off", enabled=False, status="broken"),
        health(slug="f-unreachable", status="unreachable"),
    ]
    assert [h.slug for h in sorted(rows, key=lambda h: h.rank)] == [
        "b-broken",
        "f-unreachable",
        "c-silent",
        "d-empty",
        "a-ok",
        "e-off",
    ]


# --- broken vs empty, from fixtures (plan M7 "done when") ---------------------------------------

AWRAS = "https://elauresnews.dz/wp-json/wp/v2/posts?per_page=100&_embed=wp:featuredmedia,wp:term&_fields=id,date_gmt,modified_gmt,link,title,excerpt,categories,_links,_embedded"  # noqa: E501
LISTING = (DEFAULT_CATALOG.parent / "backend/tests/fixtures/awras-ar/listing_1.json").read_bytes()


@pytest.fixture
def awras(session):
    import random

    import httpx2
    from sqlalchemy.orm import sessionmaker

    entries = [e for e in read_catalog(DEFAULT_CATALOG) if e.slug == "awras-ar"]
    load_catalog(session, entries, "test")
    session.flush()
    job = next(j for j in load_jobs(session) if j.slug == "awras-ar")
    assert job.config.listings[0] == AWRAS
    web = Web()
    web.set("https://elauresnews.dz/robots.txt", b"User-agent: *\nDisallow: /wp-admin/\n")
    fetcher = Fetcher(
        Settings(),
        transport=httpx2.MockTransport(web.handler),
        clock=FakeClock(),
        rng=random.Random(0),
    )
    factory = sessionmaker(
        bind=session.connection(), join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    return job, web, fetcher, Database(factory)


@pytest.mark.db
@pytest.mark.parametrize(
    ("body", "status", "expected"),
    [
        (LISTING, 200, "ok"),
        (b"[]", 200, "empty"),  # valid answer, no posts: nothing to repair
        # the API changed its fields: every item rejected -> repair needed
        (LISTING.replace(b'"title":', b'"headline":'), 200, "broken"),
        (b"<html><body>Maintenance</body></html>", 200, "broken"),  # not JSON at all
        (b'{"code":"rest_no_route","message":"No route"}', 404, "unreachable"),
    ],
    ids=["ok", "empty", "fields-changed", "html-instead-of-json", "api-removed"],
)
def test_broken_and_empty_sites_get_the_right_status(session, awras, body, status, expected):
    job, web, fetcher, database = awras
    web.set(AWRAS, body, status=status)
    outcome = run_poll(job, fetcher, database, NOW)
    assert outcome.status == expected
    session.expire_all()
    assert session.get(Source, job.source_id).status == expected


@pytest.mark.db
def test_status_since_moves_only_when_the_status_changes(session, awras):
    job, *_ = awras
    when = [NOW + timedelta(minutes=m) for m in range(4)]
    for moment, status in zip(when, ["ok", "ok", "broken", "broken"], strict=True):
        record_run(session, job.source_id, started_at=moment, finished_at=moment, status=status)
        session.flush()
        if moment == when[1]:
            assert session.get(Source, job.source_id).status_changed_at == when[0]
    assert session.get(Source, job.source_id).status_changed_at == when[2]


# --- endpoints -------------------------------------------------------------------------------


@pytest.mark.db
def test_health_pages(client, committed):
    db = committed
    load_catalog(db, read_catalog(DEFAULT_CATALOG), "test")
    db.commit()
    broken = db.scalar(select(Source).where(Source.slug == "aps-ar"))
    for minutes in range(3):
        moment = NOW - timedelta(minutes=10 - minutes)
        record_run(
            db,
            broken.id,
            started_at=moment,
            finished_at=moment,
            status="broken",
            error="not JSON: <script>alert(1)</script>",
        )
    db.commit()

    public = client.get("/health.json").json()
    assert public["sources"]["broken"] == 1 and "aps-ar" not in str(public)  # counts only

    assert client.get("/health").status_code == 401
    make_user(db, "org-a", "a@org-a.dz")
    login(client, "a@org-a.dz")
    assert client.get("/health/sources.json").status_code == 403  # Sabq team only

    make_user(db, "sabq", "team@sabq.dz", admin=True)
    login(client, "team@sabq.dz")
    rows = client.get("/health/sources.json").json()
    assert rows[0]["slug"] == "aps-ar" and rows[0]["needs_attention"]
    assert rows[0]["failures_in_a_row"] == 3 and rows[0]["warnings"][0].startswith("failing")
    page = client.get("/health").text
    assert "<script>alert" not in page and "&lt;script&gt;" in page  # errors are escaped
    assert page.index("aps-ar") < page.index("awras-ar")  # problems first


# --- rhythm and the state journalists see ------------------------------------------------------


def test_rhythm_needs_a_few_days_of_history():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    assert rhythm([], now) == (None, None)
    assert rhythm([now - timedelta(days=1)], now) == (None, None)


def test_rhythm_of_a_regular_source_has_no_edition():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    times = [now - timedelta(hours=5 * i) for i in range(1, 60)]
    per_day, edition = rhythm(times, now)
    assert per_day == pytest.approx(4.8, abs=0.1) and edition is None


def test_rhythm_finds_a_daily_edition_in_algiers_time():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    # 23:10 UTC is 00:10 in Algiers (UTC+1)
    times = [
        datetime(2026, 10, day, 23, minute, tzinfo=UTC)
        for day in range(10, 20)
        for minute in range(10, 20)
    ]
    per_day, edition = rhythm(times, now)
    assert edition == 0 and per_day == pytest.approx(10, abs=0.5)


@pytest.mark.parametrize(
    ("status", "warnings", "state"),
    [
        ("ok", [], "ok"),
        ("empty", [], "ok"),
        ("degraded", [], "delayed"),
        ("ok", ["silent: no new article for 3 h (usually 1 h)"], "delayed"),
        ("ok", ["stale: last successful poll 5 h ago"], "stopped"),
        ("broken", [], "stopped"),
        ("unreachable", [], "stopped"),
        ("blocked_by_robots", [], "stopped"),
    ],
)
def test_state_journalists_see(status, warnings, state):
    health = SourceHealth("s", "s", True, status, None, "rss", 300, warnings=warnings)
    assert health.state == state
