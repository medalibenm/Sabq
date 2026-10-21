"""M3: polite fetching (docs/plan.md). A fake site records every request with the fake time it
arrived, so spacing, backoff and caching are checked without waiting."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

import httpx2
import pytest

from sabq import __version__
from sabq.fetch import (
    BackingOff,
    EgressUnavailable,
    Fetcher,
    FetchError,
    ResponseTooLarge,
    RobotsDisallowed,
    RobotsRules,
    RobotsUnavailable,
)
from sabq.settings import Settings

START = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def now(self) -> datetime:
        return START + timedelta(seconds=self.t - 1000.0)

    async def sleep(self, seconds: float) -> None:
        self.t += seconds


class Site:
    """Fake web. Unrouted URLs (including robots.txt) answer 404."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.routes = {}
        self.requests: list[tuple[float, str, httpx2.Headers]] = []

    def route(self, url, status=200, body=b"", headers=None):
        self.routes[url] = lambda request: httpx2.Response(status, content=body, headers=headers)

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append((self.clock.t, str(request.url), request.headers))
        responder = self.routes.get(str(request.url))
        return responder(request) if responder else httpx2.Response(404)

    def urls(self) -> list[str]:
        return [url for _, url, _ in self.requests]

    def times(self, url: str) -> list[float]:
        return [t for t, u, _ in self.requests if u == url]


def make(**overrides):
    clock = FakeClock()
    site = Site(clock)
    settings = Settings(**{"fetch_min_host_gap_s": 5.0, "fetch_gap_jitter": 0.2, **overrides})
    fetcher = Fetcher(
        settings,
        transport=httpx2.MockTransport(site.handler),
        clock=clock,
        rng=random.Random(1),
    )
    return fetcher, site, clock


def run(coro):
    return asyncio.run(coro)


# --- robots.txt ----------------------------------------------------------------------------


def test_robots_rules_most_specific_wins_and_own_group_replaces_star():
    rules = RobotsRules.from_response(
        200,
        b"User-agent: *\nDisallow: /\nCrawl-delay: 30\n\n"
        b"User-agent: SabqBot\nDisallow: /private\nAllow: /private/ok\nDisallow: /*?s=\n",
    )
    assert rules.allows("https://a.dz/news/1")
    assert not rules.allows("https://a.dz/private/x")
    assert rules.allows("https://a.dz/private/ok")
    assert not rules.allows("https://a.dz/?s=elections")
    assert rules.crawl_delay == 0  # the `*` group's delay is not ours


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        (404, "allow_all"),
        (410, "allow_all"),
        (401, "disallow_all"),
        (403, "disallow_all"),
        (429, "unreachable"),
        (500, "unreachable"),
        (503, "unreachable"),
    ],
)
def test_robots_status_codes(status, verdict):
    assert RobotsRules.from_response(status, b"").verdict == verdict


def test_disallowed_url_is_never_requested():
    fetcher, site, _ = make()
    site.route("https://a.dz/robots.txt", body=b"User-agent: *\nDisallow: /private\n")
    site.route("https://a.dz/private/feed", body=b"secret")

    with pytest.raises(RobotsDisallowed):
        run(fetcher.get("https://a.dz/private/feed"))
    assert site.urls() == ["https://a.dz/robots.txt"]


def test_robots_403_blocks_everything():
    fetcher, site, _ = make()
    site.route("https://a.dz/robots.txt", status=403)
    with pytest.raises(RobotsDisallowed, match="403"):
        run(fetcher.get("https://a.dz/"))
    assert site.urls() == ["https://a.dz/robots.txt"]


def test_robots_unreachable_blocks_until_retry():
    fetcher, site, clock = make(robots_retry_s=900, fetch_backoff_base_s=60)
    site.route("https://a.dz/robots.txt", status=500)

    async def scenario():
        with pytest.raises(RobotsUnavailable):
            await fetcher.get("https://a.dz/news")
        clock.t += 100  # backoff over, robots.txt verdict still cached
        with pytest.raises(RobotsUnavailable):
            await fetcher.get("https://a.dz/news")
        site.route("https://a.dz/robots.txt", status=404)
        clock.t += 900
        return await fetcher.get("https://a.dz/news")

    assert run(scenario()).status == 404
    assert site.urls() == [
        "https://a.dz/robots.txt",
        "https://a.dz/robots.txt",
        "https://a.dz/news",
    ]


def test_robots_cached_for_a_day():
    fetcher, site, clock = make()

    async def scenario():
        await fetcher.get("https://a.dz/1")
        await fetcher.get("https://a.dz/2")
        clock.t += 86400
        await fetcher.get("https://a.dz/3")

    run(scenario())
    assert site.urls().count("https://a.dz/robots.txt") == 2


# --- pacing ----------------------------------------------------------------------------------


def gaps(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:], strict=False)]


def test_one_host_is_spaced_and_other_hosts_are_not_delayed():
    fetcher, site, _ = make()

    async def scenario():
        for n in range(4):
            await fetcher.get(f"https://a.dz/{n}")
        await fetcher.get("https://b.dz/0")

    run(scenario())
    a_times = [t for t, url, _ in site.requests if url.startswith("https://a.dz/")]
    assert all(5.0 <= gap <= 6.0 for gap in gaps(a_times))  # 5 s + up to 20 % jitter
    assert len(set(round(g, 6) for g in gaps(a_times))) > 1  # jitter really varies
    b_robots = site.times("https://b.dz/robots.txt")[0]
    assert b_robots < a_times[-1] + 5.0  # b.dz did not wait for a.dz's gap


def test_concurrent_requests_to_one_host_are_serialised():
    fetcher, site, _ = make()

    async def scenario():
        await asyncio.gather(*(fetcher.get(f"https://a.dz/{n}") for n in range(3)))

    run(scenario())
    assert all(gap >= 5.0 for gap in gaps([t for t, _, _ in site.requests]))


def test_crawl_delay_is_honoured():
    fetcher, site, _ = make()
    site.route("https://a.dz/robots.txt", body=b"User-agent: *\nCrawl-delay: 10\n")

    async def scenario():
        for n in range(3):
            await fetcher.get(f"https://a.dz/{n}")

    run(scenario())
    assert all(10.0 <= gap <= 12.0 for gap in gaps([t for t, _, _ in site.requests][1:]))


# --- conditional requests --------------------------------------------------------------------


def test_etag_and_last_modified_are_sent_back():
    fetcher, site, _ = make()
    validators = {"ETag": '"v1"', "Last-Modified": "Wed, 21 Oct 2026 10:00:00 GMT"}
    site.route("https://a.dz/feed", body=b"<rss/>", headers=validators)

    async def scenario():
        first = await fetcher.get("https://a.dz/feed")
        site.route("https://a.dz/feed", status=304)
        second = await fetcher.get("https://a.dz/feed")
        return first, second

    first, second = run(scenario())
    assert (first.status, first.content, first.not_modified) == (200, b"<rss/>", False)
    assert second.not_modified
    sent = site.requests[-1][2]
    assert sent["if-none-match"] == '"v1"'
    assert sent["if-modified-since"] == "Wed, 21 Oct 2026 10:00:00 GMT"
    assert "if-none-match" not in site.requests[1][2]  # first request had nothing to send


# --- backoff ---------------------------------------------------------------------------------


def test_5xx_backs_off_exponentially_without_sending():
    fetcher, site, clock = make(fetch_backoff_base_s=60)
    site.route("https://a.dz/feed", status=503)

    async def scenario():
        await fetcher.get("https://a.dz/feed")  # failure 1: 60 s
        with pytest.raises(BackingOff) as first:
            await fetcher.get("https://a.dz/feed")
        clock.t += 60
        await fetcher.get("https://a.dz/feed")  # failure 2: 120 s
        clock.t += 60
        with pytest.raises(BackingOff) as second:
            await fetcher.get("https://a.dz/feed")
        clock.t += 60
        site.route("https://a.dz/feed", body=b"ok")
        ok = await fetcher.get("https://a.dz/feed")
        await fetcher.get("https://a.dz/feed")  # success reset the failures: no backoff
        return first.value, second.value, ok

    first, second, ok = run(scenario())
    assert first.retry_in == pytest.approx(60, abs=0.01)
    assert second.retry_in == pytest.approx(60, abs=0.01)  # 120 s, 60 s already waited
    assert ok.status == 200
    assert site.urls().count("https://a.dz/feed") == 4


def test_retry_after_seconds_and_http_date():
    fetcher, site, clock = make(fetch_backoff_base_s=60)
    site.route("https://a.dz/s", status=429, headers={"Retry-After": "300"})
    later = (START + timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    site.route("https://b.dz/d", status=503, headers={"Retry-After": later})

    async def scenario():
        await fetcher.get("https://a.dz/s")
        await fetcher.get("https://b.dz/d")
        errors = []
        for url in ("https://a.dz/s", "https://b.dz/d"):
            with pytest.raises(BackingOff) as error:
                await fetcher.get(url)
            errors.append(error.value.retry_in)
        return errors

    a_wait, b_wait = run(scenario())
    # b.dz's own robots.txt + gap took a few seconds of the fake clock in between
    assert 290 < a_wait <= 300
    assert 7180 < b_wait <= 7200


def test_network_error_backs_off():
    fetcher, site, _ = make()

    def refuse(request):
        raise httpx2.ConnectError("connection refused", request=request)

    site.route("https://a.dz/robots.txt")
    site.routes["https://a.dz/feed"] = refuse

    async def scenario():
        with pytest.raises(FetchError, match="ConnectError"):
            await fetcher.get("https://a.dz/feed")
        with pytest.raises(BackingOff):
            await fetcher.get("https://a.dz/feed")

    run(scenario())
    assert site.urls().count("https://a.dz/feed") == 1


# --- redirects, egress, limits, identity -------------------------------------------------------


def test_redirect_to_another_host_checks_that_hosts_robots():
    fetcher, site, _ = make()
    site.route("https://a.dz/old", status=301, headers={"Location": "https://b.dz/new"})
    site.route("https://b.dz/new", body=b"moved")
    site.route("https://a.dz/blocked", status=302, headers={"Location": "https://c.dz/x"})
    site.route("https://c.dz/robots.txt", body=b"User-agent: SabqBot\nDisallow: /\n")

    async def scenario():
        result = await fetcher.get("https://a.dz/old")
        with pytest.raises(RobotsDisallowed):
            await fetcher.get("https://a.dz/blocked")
        return result

    result = run(scenario())
    assert (result.url, result.content, result.redirects) == (
        "https://b.dz/new",
        b"moved",
        ("https://a.dz/old",),
    )
    assert "https://b.dz/robots.txt" in site.urls()
    assert "https://c.dz/x" not in site.urls()


def test_dz_proxy_egress():
    fetcher, site, clock = make()
    with pytest.raises(EgressUnavailable):
        run(fetcher.get("https://a.dz/", egress="dz_proxy"))

    proxied = Site(clock)
    proxied.route("https://a.dz/", body=b"via proxy")
    fetcher = Fetcher(
        Settings(),
        transport=httpx2.MockTransport(site.handler),
        proxy_transport=httpx2.MockTransport(proxied.handler),
        clock=clock,
    )
    result = run(fetcher.get("https://a.dz/", egress="dz_proxy"))
    assert result.content == b"via proxy"
    assert site.requests == []
    assert proxied.urls() == ["https://a.dz/robots.txt", "https://a.dz/"]


def test_oversized_response_is_refused():
    fetcher, site, _ = make(fetch_max_bytes=1000)
    site.route("https://a.dz/huge", body=b"x" * 5000)
    with pytest.raises(ResponseTooLarge):
        run(fetcher.get("https://a.dz/huge"))


def test_every_request_identifies_as_sabqbot():
    fetcher, site, _ = make(sabqbot_contact_url="https://sabq.example/bot")
    run(fetcher.get("https://a.dz/"))
    agents = {headers["user-agent"] for _, _, headers in site.requests}
    assert agents == {f"SabqBot/{__version__} (+https://sabq.example/bot)"}
