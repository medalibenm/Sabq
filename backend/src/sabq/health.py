"""Source health (plan M7, docs/architecture.md#breakage-detection).

The worker sets each source's status after every poll (`sabq.ingest.poller`); this module adds
what needs history, as warnings:

  silent        no new article for more than 3x the source's usual quiet period
  failing       several polls in a row failed (the status says why)
  fewer items   the last listing had far fewer items than usual (layout change, partial page)
  stale         no successful poll for a long time (worker down, or the source keeps failing)

"Usual quiet period": the median of the N longest gaps between consecutive new articles in
the last 14 days, N = the number of days the history covers (at most 14), i.e. about one normal
daily quiet period. A plain median gap would cry wolf for bursty sources (Awras uploads ~70
articles in 10 minutes once a day: one long gap a day, ~70 tiny ones). Fewer than 3 gaps: not
enough history yet, no silence warning. Baseline articles never count.

Sources with problems are listed first, with how long they have been in their state.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sabq.db.models import Article, FetchRun, Source

GAP_WINDOW = timedelta(days=14)
GAPS_USED = 14
MIN_GAPS = 3
SILENCE_FACTOR = 3
FAILING_AFTER = 3  # failed polls in a row
FEWER_ITEMS_RATIO = 0.3
RUNS_FOR_USUAL_ITEMS = 20
DELAY_WINDOW = timedelta(days=7)

# problems first; then warnings; empty and ok last
STATUS_RANK = {
    "broken": 0,
    "unreachable": 1,
    "blocked_by_robots": 2,
    "degraded": 4,
    "empty": 6,
    "ok": 7,
}


@dataclass
class SourceHealth:
    slug: str
    name: str
    enabled: bool
    status: str
    status_since: datetime | None
    access_method: str
    poll_interval_s: int
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    failures_in_a_row: int = 0
    new_last_24h: int = 0
    median_delay_s: float | None = None  # last 7 days
    last_new_at: datetime | None = None
    usual_quiet_s: float | None = None
    last_items_seen: int | None = None
    usual_items_seen: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def rank(self) -> tuple:
        if not self.enabled:
            return (9, self.slug)
        rank = STATUS_RANK.get(self.status, 5)
        if any(w.startswith("silent") for w in self.warnings):
            rank = min(rank, 3)
        elif self.warnings:
            rank = min(rank, 5)
        return (rank, self.slug)

    @property
    def needs_attention(self) -> bool:
        return self.enabled and (self.rank[0] < 6)


def usual_quiet_period(times: list[datetime]) -> float | None:
    """Median of the longest gaps between consecutive new articles, one per day covered (s)."""
    ordered = sorted(times)
    gaps = [(b - a).total_seconds() for a, b in zip(ordered, ordered[1:], strict=False)]
    if len(gaps) < MIN_GAPS:
        return None
    days = (ordered[-1] - ordered[0]).total_seconds() / 86400
    used = max(1, min(GAPS_USED, round(days)))
    return statistics.median(sorted(gaps, reverse=True)[:used])


def silence_threshold(usual_quiet_s: float, poll_interval_s: int) -> float:
    return max(SILENCE_FACTOR * usual_quiet_s, 2 * poll_interval_s, 3600)


def warnings_for(health: SourceHealth, now: datetime) -> list[str]:
    found = []
    if health.usual_quiet_s and health.last_new_at:
        quiet = (now - health.last_new_at).total_seconds()
        if quiet > silence_threshold(health.usual_quiet_s, health.poll_interval_s):
            found.append(
                f"silent: no new article for {human(quiet)} (usually {human(health.usual_quiet_s)})"
            )
    if health.failures_in_a_row >= FAILING_AFTER:
        found.append(f"failing: {health.failures_in_a_row} polls in a row")
    if (
        health.usual_items_seen
        and health.last_items_seen is not None
        and health.last_items_seen < FEWER_ITEMS_RATIO * health.usual_items_seen
        and health.status not in ("empty", "broken")
    ):
        found.append(
            f"fewer items: {health.last_items_seen} in the last listing "
            f"(usually {health.usual_items_seen:.0f})"
        )
    stale_after = max(6 * health.poll_interval_s, 3 * 3600)
    since_success = (now - health.last_success_at).total_seconds() if health.last_success_at else 0
    if since_success > stale_after:
        found.append(f"stale: last successful poll {human(since_success)} ago")
    return found


def human(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 3600:
        return f"{max(seconds // 60, 1)} min"
    if seconds < 2 * 86400:
        return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"
    return f"{seconds // 86400} days {seconds % 86400 // 3600} h"


async def source_health(db: AsyncSession, now: datetime) -> list[SourceHealth]:
    sources = list(await db.scalars(select(Source).order_by(Source.slug)))
    by_id = {
        s.id: SourceHealth(
            slug=s.slug,
            name=s.name,
            enabled=s.enabled,
            status=s.status,
            status_since=s.status_changed_at,
            access_method=s.access_method,
            poll_interval_s=s.poll_interval_s,
        )
        for s in sources
    }

    ok_run = FetchRun.error.is_(None)
    for source_id, last_ok, last_failed in await db.execute(
        select(
            FetchRun.source_id,
            func.max(FetchRun.started_at).filter(ok_run),
            func.max(FetchRun.started_at).filter(~ok_run),
        ).group_by(FetchRun.source_id)
    ):
        if source_id in by_id:
            by_id[source_id].last_success_at, by_id[source_id].last_failure_at = (
                last_ok,
                last_failed,
            )

    failed = (
        select(
            FetchRun.source_id,
            FetchRun.error,
            func.row_number()
            .over(partition_by=FetchRun.source_id, order_by=FetchRun.started_at.desc())
            .label("n"),
        )
        .where(~ok_run)
        .subquery()
    )
    last_errors = select(failed.c.source_id, failed.c.error).where(failed.c.n == 1)
    for source_id, error in await db.execute(last_errors):
        if source_id in by_id:
            by_id[source_id].last_error = error

    # recent runs: failures in a row, items seen (last and usual)
    numbered = select(
        FetchRun.source_id,
        FetchRun.error,
        FetchRun.items_seen,
        func.row_number()
        .over(partition_by=FetchRun.source_id, order_by=FetchRun.started_at.desc())
        .label("n"),
    ).subquery()
    runs = defaultdict(list)
    for source_id, error, items_seen, _ in await db.execute(
        select(numbered).where(numbered.c.n <= RUNS_FOR_USUAL_ITEMS).order_by(numbered.c.n)
    ):
        runs[source_id].append((error, items_seen))
    for source_id, recent in runs.items():
        health = by_id.get(source_id)
        if health is None:
            continue
        health.failures_in_a_row = next(
            (i for i, (error, _) in enumerate(recent) if error is None), len(recent)
        )
        seen = [items for error, items in recent if error is None]
        if seen:
            health.last_items_seen = seen[0]
            nonzero = [n for n in seen if n > 0]
            health.usual_items_seen = statistics.median(nonzero) if nonzero else None

    new = Article.baseline.is_(False)
    for source_id, count, delay, last_new in await db.execute(
        select(
            Article.source_id,
            func.count().filter(Article.first_seen_at > now - timedelta(hours=24)),
            func.percentile_cont(0.5)
            .within_group(Article.detection_delay_s)
            .filter(Article.first_seen_at > now - DELAY_WINDOW),
            func.max(Article.first_seen_at),
        )
        .where(new)
        .group_by(Article.source_id)
    ):
        if source_id in by_id:
            health = by_id[source_id]
            health.new_last_24h, health.median_delay_s, health.last_new_at = count, delay, last_new

    times = defaultdict(list)
    for source_id, first_seen in await db.execute(
        select(Article.source_id, Article.first_seen_at).where(
            new, Article.first_seen_at > now - GAP_WINDOW
        )
    ):
        times[source_id].append(first_seen)
    for source_id, seen in times.items():
        if source_id in by_id:
            by_id[source_id].usual_quiet_s = usual_quiet_period(seen)

    for health in by_id.values():
        health.warnings = warnings_for(health, now)
    return sorted(by_id.values(), key=lambda h: h.rank)
