"""Polite HTTP fetching: every request Sabq sends to a source goes through `Fetcher.get`.

For each request (docs/architecture.md, layer 1; docs/plan.md M3):
  - robots.txt is checked live for the URL's origin first (cached `robots_ttl_s`); a disallowed
    URL raises `RobotsDisallowed` and nothing is sent;
  - one request at a time per host, at least `fetch_min_host_gap_s` apart, or the site's
    `Crawl-delay` if longer, each gap 0-20 % longer (jitter, never shorter);
  - the `ETag` / `Last-Modified` seen for a URL are sent back; `304` comes back `not_modified`;
  - 429, 5xx or a network error puts the host in backoff (exponential, or the site's
    `Retry-After` if longer); while it lasts, requests raise `BackingOff` without being sent;
  - redirects are followed one hop at a time, so every hop gets the same checks;
  - `egress="dz_proxy"` requests go through `DZ_PROXY_URL`.

The worker runs a single `Fetcher`. Its state is in memory: a restart re-reads robots.txt and
forgets validators, which costs one full response per URL.
"""

import asyncio
import email.utils
import logging
import random
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

import httpx2

from sabq.fetch.robots import RobotsRules
from sabq.settings import Settings

log = logging.getLogger(__name__)

Egress = Literal["default", "dz_proxy"]
MAX_REDIRECTS = 5
REDIRECTS = {301, 302, 303, 307, 308}
MAX_VALIDATORS = 10_000  # URLs whose ETag / Last-Modified we keep (least recently used dropped)


class FetchError(Exception):
    """The request could not be sent or completed."""


class RobotsDisallowed(FetchError):
    """robots.txt does not allow this URL for SabqBot. The source is `blocked_by_robots`."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{url}: not allowed by robots.txt ({reason})")
        self.url, self.reason = url, reason


class RobotsUnavailable(FetchError):
    """robots.txt cannot be read right now, so nothing is fetched from that origin."""


class BackingOff(FetchError):
    """The host failed recently; no request is sent until the backoff ends."""

    def __init__(self, host: str, retry_in: float):
        super().__init__(f"{host}: backing off for {retry_in:.0f} s")
        self.host, self.retry_in = host, retry_in


class EgressUnavailable(FetchError):
    """The source needs an egress that is not configured (e.g. `dz_proxy` without a URL)."""


class ResponseTooLarge(FetchError):
    pass


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def now(self) -> datetime: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass(frozen=True)
class FetchResult:
    url: str  # final URL, after redirects
    status: int
    headers: httpx2.Headers
    content: bytes
    elapsed_ms: int  # the final request only, not waiting for the host
    redirects: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def not_modified(self) -> bool:
        return self.status == 304


@dataclass
class _Host:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_at: float = 0.0  # monotonic time the next request may start
    backoff_until: float = 0.0
    failures: int = 0
    crawl_delay: float = 0.0


@dataclass
class _CachedRobots:
    rules: RobotsRules
    expires_at: float


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        proxy_transport: httpx2.AsyncBaseTransport | None = None,
        clock: Clock | None = None,
        rng: random.Random | None = None,
    ):
        self.settings = settings
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random()
        common = {
            "headers": {"User-Agent": settings.user_agent, "Accept": "*/*"},
            "timeout": httpx2.Timeout(settings.fetch_timeout_s),
            "http2": True,
            "follow_redirects": False,  # followed hop by hop in `get`
            "trust_env": False,  # egress is chosen per source, never by environment proxies
        }
        self._clients = {"default": httpx2.AsyncClient(transport=transport, **common)}
        if proxy_transport is not None:
            self._clients["dz_proxy"] = httpx2.AsyncClient(transport=proxy_transport, **common)
        elif settings.dz_proxy_url:
            self._clients["dz_proxy"] = httpx2.AsyncClient(proxy=settings.dz_proxy_url, **common)
        self._hosts: dict[str, _Host] = {}
        self._robots: dict[str, _CachedRobots] = {}
        self._validators: OrderedDict[str, dict[str, str]] = OrderedDict()

    async def __aenter__(self) -> "Fetcher":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()

    async def get(self, url: str, *, egress: Egress = "default") -> FetchResult:
        client = self._client(egress)
        redirects: list[str] = []
        for _ in range(MAX_REDIRECTS + 1):
            rules = await self._robots_for(url, client)
            if not rules.allows(url):
                log.warning("robots.txt disallows %s (%s)", url, rules.reason)
                raise RobotsDisallowed(url, rules.reason)
            status, headers, content, elapsed_ms = await self._send(
                client, url, self._conditional_headers(url)
            )
            if status in REDIRECTS and "location" in headers:
                redirects.append(url)
                url = urljoin(url, headers["location"])
                continue
            self._remember_validators(url, status, headers)
            return FetchResult(url, status, headers, content, elapsed_ms, tuple(redirects))
        raise FetchError(f"{redirects[0]}: more than {MAX_REDIRECTS} redirects")

    # --- robots.txt ---------------------------------------------------------------------------

    async def _robots_for(self, url: str, client: httpx2.AsyncClient) -> RobotsRules:
        origin = _origin(url)
        cached = self._robots.get(origin)
        if cached is None or self.clock.monotonic() >= cached.expires_at:
            rules = await self._fetch_robots(origin, client)
            ttl = (
                self.settings.robots_retry_s
                if rules.verdict == "unreachable"
                else self.settings.robots_ttl_s
            )
            cached = self._robots[origin] = _CachedRobots(rules, self.clock.monotonic() + ttl)
            self._host(urlsplit(origin).hostname or "").crawl_delay = rules.crawl_delay
        if cached.rules.verdict == "unreachable":
            raise RobotsUnavailable(f"{origin}: {cached.rules.reason}")
        return cached.rules

    async def _fetch_robots(self, origin: str, client: httpx2.AsyncClient) -> RobotsRules:
        url = f"{origin}/robots.txt"
        try:
            for _ in range(MAX_REDIRECTS + 1):
                status, headers, content, _ = await self._send(client, url, {})
                if status in REDIRECTS and "location" in headers:
                    url = urljoin(url, headers["location"])
                    continue
                return RobotsRules.from_response(status, content)
        except BackingOff:
            raise  # not a verdict on robots.txt; try again when the backoff ends
        except FetchError as exc:
            return RobotsRules.unreachable(str(exc))
        return RobotsRules.unreachable(f"robots.txt: more than {MAX_REDIRECTS} redirects")

    # --- one request, paced per host -------------------------------------------------------------

    async def _send(
        self, client: httpx2.AsyncClient, url: str, headers: dict[str, str]
    ) -> tuple[int, httpx2.Headers, bytes, int]:
        hostname = urlsplit(url).hostname or ""
        host = self._host(hostname)
        async with host.lock:
            now = self.clock.monotonic()
            if now < host.backoff_until:
                raise BackingOff(hostname, host.backoff_until - now)
            if now < host.next_at:
                await self.clock.sleep(host.next_at - now)
            started = self.clock.monotonic()
            try:
                status, response_headers, content = await self._request(client, url, headers)
            except httpx2.TransportError as exc:  # connection errors and timeouts
                self._back_off(host, hostname, None)
                raise FetchError(f"{url}: {type(exc).__name__}: {exc}") from exc
            finally:
                host.next_at = self.clock.monotonic() + self._gap(host)
            elapsed_ms = int((self.clock.monotonic() - started) * 1000)
            log.debug("GET %s -> %s in %d ms", url, status, elapsed_ms)
            if status == 429 or status >= 500:
                self._back_off(host, hostname, self._retry_after(response_headers))
            else:
                host.failures = 0
            return status, response_headers, content, elapsed_ms

    async def _request(
        self, client: httpx2.AsyncClient, url: str, headers: dict[str, str]
    ) -> tuple[int, httpx2.Headers, bytes]:
        limit = self.settings.fetch_max_bytes
        async with client.stream("GET", url, headers=headers) as response:
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ResponseTooLarge(f"{url}: larger than {limit} bytes")
                chunks.append(chunk)
            return response.status_code, response.headers, b"".join(chunks)

    def _gap(self, host: _Host) -> float:
        base = max(self.settings.fetch_min_host_gap_s, host.crawl_delay)
        return base * (1 + self.rng.uniform(0, self.settings.fetch_gap_jitter))

    def _back_off(self, host: _Host, hostname: str, retry_after: float | None) -> None:
        host.failures += 1
        delay = min(
            self.settings.fetch_backoff_base_s * 2 ** (host.failures - 1),
            self.settings.fetch_backoff_max_s,
        )
        if retry_after is not None:
            delay = max(delay, min(retry_after, self.settings.fetch_retry_after_max_s))
        host.backoff_until = self.clock.monotonic() + delay
        log.warning("%s: failure %d, backing off %.0f s", hostname, host.failures, delay)

    def _retry_after(self, headers: httpx2.Headers) -> float | None:
        value = headers.get("retry-after", "").strip()
        if not value:
            return None
        if value.isdigit():
            return float(value)
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - self.clock.now()).total_seconds())

    # --- conditional requests ------------------------------------------------------------------

    def _conditional_headers(self, url: str) -> dict[str, str]:
        seen = self._validators.get(url, {})
        headers = {}
        if "etag" in seen:
            headers["If-None-Match"] = seen["etag"]
        if "last-modified" in seen:
            headers["If-Modified-Since"] = seen["last-modified"]
        return headers

    def _remember_validators(self, url: str, status: int, headers: httpx2.Headers) -> None:
        if status == 304:
            if url in self._validators:
                self._validators.move_to_end(url)
            return
        if not 200 <= status < 300:
            return
        seen = {name: headers[name] for name in ("etag", "last-modified") if name in headers}
        if seen:
            self._validators[url] = seen
            self._validators.move_to_end(url)
            while len(self._validators) > MAX_VALIDATORS:
                self._validators.popitem(last=False)
        else:
            self._validators.pop(url, None)

    # --- helpers -------------------------------------------------------------------------------

    def _client(self, egress: Egress) -> httpx2.AsyncClient:
        try:
            return self._clients[egress]
        except KeyError:
            raise EgressUnavailable(f"egress {egress!r} is not configured (DZ_PROXY_URL)") from None

    def _host(self, hostname: str) -> _Host:
        return self._hosts.setdefault(hostname, _Host())


def _origin(url: str) -> str:
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"
