"""The worker's scheduler (plan M5): polls each enabled source at its interval.

- Each source is due `poll_interval_s` after its last poll, ±20 % (jitter); after a worker
  restart, after its last `fetch_runs` row (plus a few seconds' stagger).
- A few sources are polled at the same time (`ingest_concurrency`); the fetcher still sends one
  request at a time per host.
- Sources are re-read from the database every tick, so `catalog load` takes effect without a
  restart; a source whose stored config no longer validates is skipped and logged.
- A host in backoff: the source waits for the backoff. Blocked by robots.txt: re-checked once
  the robots.txt cache expires (24 h), not every interval.
"""

import asyncio
import contextlib
import logging
import random
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sabq.db.models import FetchRun, Source
from sabq.extract.config import SourceConfig
from sabq.fetch import Fetcher
from sabq.fetch.client import Clock, SystemClock
from sabq.ingest.poller import Database, Job, Outcome, poll
from sabq.settings import Settings

log = logging.getLogger(__name__)
STARTUP_STAGGER_S = 10.0


def load_jobs(session: Session) -> list[Job]:
    rows = session.execute(
        select(Source, func.max(FetchRun.started_at))
        .outerjoin(FetchRun, FetchRun.source_id == Source.id)
        .where(Source.enabled.is_(True))
        .group_by(Source.id)
        .order_by(Source.id)
    ).all()
    jobs = []
    for source, last_started_at in rows:
        try:
            config = SourceConfig.of(source.config)
        except ValidationError as exc:
            log.error("%s: stored config is invalid, not polled: %s", source.slug, exc)
            continue
        jobs.append(
            Job(
                source_id=source.id,
                slug=source.slug,
                language=source.language,
                egress=source.egress,
                poll_interval_s=source.poll_interval_s,
                status=source.status,
                config=config,
                last_started_at=last_started_at,
            )
        )
    return jobs


class Scheduler:
    def __init__(
        self,
        settings: Settings,
        fetcher: Fetcher,
        db: Database,
        *,
        clock: Clock | None = None,
        rng: random.Random | None = None,
    ):
        self.settings = settings
        self.fetcher = fetcher
        self.db = db
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random()
        self.next_at: dict[int, float] = {}  # source id -> monotonic due time
        self.running: dict[int, asyncio.Task] = {}
        self._slots = asyncio.Semaphore(settings.ingest_concurrency)

    async def tick(self) -> float:
        """Start every due source; return seconds until the next one is due."""
        jobs = await self.db.run(load_jobs)
        now = self.clock.monotonic()
        enabled = {job.source_id for job in jobs}
        for source_id in set(self.next_at) - enabled:
            del self.next_at[source_id]
        for job in jobs:
            if job.source_id in self.running:
                continue
            due = self.next_at.setdefault(job.source_id, now + self._first_delay(job))
            if due <= now:
                self.running[job.source_id] = asyncio.create_task(self._poll(job))
        pending = [t for sid, t in self.next_at.items() if sid not in self.running]
        return max(0.0, min(pending) - now) if pending else self.settings.worker_tick_seconds

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                wait = await self.tick()
            except Exception:  # database down, etc.: keep the worker alive
                log.exception("scheduler tick failed")
                wait = self.settings.worker_tick_seconds
            wait = min(max(wait, 0.5), self.settings.worker_tick_seconds)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=wait)
        await self.drain()

    async def drain(self) -> None:
        """Let running polls finish (each is short); cancel them if the worker is killed."""
        if self.running:
            await asyncio.gather(*self.running.values(), return_exceptions=True)

    def _first_delay(self, job: Job) -> float:
        stagger = self.rng.uniform(0, STARTUP_STAGGER_S)
        if job.last_started_at is None:
            return stagger
        since = (datetime.now(UTC) - job.last_started_at).total_seconds()
        return max(0.0, job.poll_interval_s - since) + stagger

    async def _poll(self, job: Job) -> None:
        delay = self._jittered(job.poll_interval_s)
        try:
            async with self._slots:
                outcome = await poll(job, self.fetcher, self.db, self.settings)
            delay = self._next_delay(job, outcome)
        except Exception:
            log.exception("%s: poll failed", job.slug)
        finally:  # next due time first, so a tick in between can't start it again
            self.next_at[job.source_id] = self.clock.monotonic() + delay
            self.running.pop(job.source_id, None)

    def _next_delay(self, job: Job, outcome: Outcome) -> float:
        if outcome.status is None:  # backing off
            return max(outcome.retry_in or 0.0, 1.0)
        if outcome.status == "blocked_by_robots":
            return max(self._jittered(job.poll_interval_s), self.settings.robots_ttl_s)
        return self._jittered(job.poll_interval_s)

    def _jittered(self, interval: float) -> float:
        jitter = self.settings.ingest_jitter
        return interval * self.rng.uniform(1 - jitter, 1 + jitter)
