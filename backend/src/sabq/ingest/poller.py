"""One poll of one source (plan M5): fetch its listings, extract, read article pages if the
config asks, store, record the run and the source status.

Source status after a poll:
  ok                  articles extracted, nothing rejected (or every listing unchanged, 304)
  degraded            articles extracted, but some items were rejected or dates unreadable
  empty               the listings answered and are valid, but hold no articles
  broken              the response is not what the config expects, or every item was rejected
  blocked_by_robots   robots.txt disallows a listing (no request was sent)
  unreachable         network error, HTTP error, or robots.txt unreadable
A host in backoff skips the poll entirely: nothing is recorded, the scheduler waits.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from sabq.extract.config import SourceConfig
from sabq.extract.extractor import (
    ExtractedItem,
    ExtractError,
    ListingResult,
    extract_listing,
    merge_listings,
)
from sabq.extract.page import enrich
from sabq.fetch import BackingOff, Fetcher, FetchError, RobotsDisallowed
from sabq.ingest.store import StoreResult, is_baseline, known_external_ids, record_run, store_items
from sabq.settings import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    source_id: int
    slug: str
    language: str
    egress: str
    poll_interval_s: int
    status: str
    config: SourceConfig
    last_started_at: datetime | None = None


@dataclass
class Outcome:
    status: str | None  # None: skipped because the host is backing off
    retry_in: float | None = None
    seen: int = 0
    new: int = 0
    baseline: int = 0
    updated: int = 0
    error: str | None = None


class Database:
    """Runs a function with a session in a worker thread, in one transaction (committed)."""

    def __init__(self, factory: sessionmaker):
        self.factory = factory

    async def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        def work():
            with self.factory.begin() as session:
                return fn(session, *args, **kwargs)

        return await asyncio.to_thread(work)


class _ListingFailed(FetchError):
    def __init__(self, url: str, status: int):
        super().__init__(f"{url}: HTTP {status}")
        self.status = status


async def poll(
    job: Job,
    fetcher: Fetcher,
    db: Database,
    settings: Settings,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Outcome:
    started = now()
    http_status: int | None = None
    try:
        results: list[ListingResult] = []
        for url in job.config.listings:
            response = await fetcher.get(url, egress=job.egress)
            http_status = response.status
            if response.not_modified:
                continue
            if not response.ok:
                raise _ListingFailed(url, response.status)
            results.append(extract_listing(job.config, url, response.content))
    except BackingOff as exc:
        log.info("%s: skipped, %s", job.slug, exc)
        return Outcome(None, retry_in=exc.retry_in)
    except RobotsDisallowed as exc:
        return await _failed(job, db, started, now, "blocked_by_robots", str(exc), None)
    except ExtractError as exc:
        return await _failed(job, db, started, now, "broken", str(exc), http_status)
    except FetchError as exc:  # network, HTTP error, robots.txt unreadable, too large
        status = exc.status if isinstance(exc, _ListingFailed) else None
        return await _failed(job, db, started, now, "unreachable", str(exc), status)

    items = merge_listings(results)
    status = _status(results, items)
    gap = timedelta(seconds=settings.ingest_baseline_gap_s)
    baseline = await db.run(is_baseline, job.source_id, started, gap)
    if job.config.article_page and items and not baseline:
        items = await _read_pages(job, fetcher, db, items, settings.ingest_max_article_pages)

    def store_and_record(session: Session) -> StoreResult:
        stored = store_items(
            session, job.source_id, job.language, items, now=now(), baseline=baseline
        )
        record_run(
            session,
            job.source_id,
            started_at=started,
            finished_at=now(),
            status=status,
            http_status=http_status,
            items_seen=len(items),
            stored=stored,
        )
        return stored

    stored = await db.run(store_and_record)
    rejected = sum(len(r.rejected) for r in results)
    log.info(
        "%s: %d seen, %d new, %d baseline, %d updated, %d rejected, status %s",
        job.slug,
        len(items),
        len(stored.new),
        stored.baseline,
        stored.updated,
        rejected,
        status,
    )
    if status != job.status:
        log.warning("%s: status %s -> %s", job.slug, job.status, status)
    return Outcome(
        status,
        seen=len(items),
        new=len(stored.new),
        baseline=stored.baseline,
        updated=stored.updated,
    )


def _status(results: list[ListingResult], items: list[ExtractedItem]) -> str:
    if not results:
        return "ok"  # every listing answered 304: unchanged
    rejected = sum(len(r.rejected) for r in results)
    problems = sum(len(r.problems) for r in results)
    if not items:
        return "broken" if rejected else "empty"
    return "degraded" if rejected or problems else "ok"


async def _failed(job, db, started, now, status, error, http_status) -> Outcome:
    log.warning("%s: %s (%s)", job.slug, status, error)

    def record(session: Session) -> None:
        record_run(
            session,
            job.source_id,
            started_at=started,
            finished_at=now(),
            status=status,
            http_status=http_status,
            error=error,
        )

    await db.run(record)
    return Outcome(status, error=error)


async def _read_pages(
    job: Job, fetcher: Fetcher, db: Database, items: list[ExtractedItem], budget: int
) -> list[ExtractedItem]:
    """Fill what the listing lacks from new articles' own pages (decision 2026-10-21)."""
    known = await db.run(known_external_ids, job.source_id, items)
    fresh = [item for item in items if item.external_id not in known]
    enriched: dict[str, ExtractedItem] = {}
    for item in fresh[:budget]:
        try:
            page = await fetcher.get(item.url, egress=job.egress)
        except BackingOff:
            break
        except FetchError as exc:  # includes a page path disallowed by robots.txt
            log.info("%s: article page %s not read: %s", job.slug, item.url, exc)
            continue
        if page.ok:
            enriched[item.external_id] = enrich(
                item,
                job.config.article_page,
                page.content,
                naive_tz=job.config.dates.published_tz,
                lead_max=job.config.lead_max_chars,
            )
    if len(fresh) > budget:
        log.info("%s: %d new articles, pages read for %d", job.slug, len(fresh), budget)
    return [enriched.get(item.external_id, item) for item in items]
