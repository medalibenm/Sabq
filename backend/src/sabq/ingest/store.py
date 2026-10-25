"""Storing one poll (plan M5). Everything for a poll happens in one transaction: articles,
versions, wilayas, the `fetch_runs` row, the source status, and the `NOTIFY` announcing new
articles (delivered by PostgreSQL only if the transaction commits).

  - An article is known by `(source, external_id)`, else by `(source, canonical_url_key)`.
  - Known: `last_seen_at` moves; a changed title / lead / image (`content_hash`) makes a new
    version. A value the listing does not carry (e.g. a lead read from the page) is kept.
  - New: stored with `first_seen_at`, its source's wilayas (method `source`), version 1. On a
    baseline poll it is marked `baseline` and not announced (decision 2026-10-21).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from sabq.db.models import Article, ArticleVersion, ArticleWilaya, FetchRun, Source, SourceWilaya
from sabq.extract.extractor import ExtractedItem, content_hash

NOTIFY_CHANNEL = "sabq_new_articles"
NOTIFY_MAX_IDS = 500  # keeps each payload far below PostgreSQL's 8000-byte limit


@dataclass
class StoreResult:
    new: list[int] = field(default_factory=list)  # announced article ids
    baseline: int = 0
    updated: int = 0
    unchanged: int = 0


def is_baseline(session: Session, source_id: int, now: datetime, gap: timedelta) -> bool:
    """First successful poll ever, or the last one is older than `gap`."""
    last_ok = session.scalar(
        select(func.max(FetchRun.started_at)).where(
            FetchRun.source_id == source_id, FetchRun.error.is_(None)
        )
    )
    return last_ok is None or now - last_ok > gap


def known_external_ids(session: Session, source_id: int, items: list[ExtractedItem]) -> set[str]:
    """External ids of `items` that are already stored (matched by id or canonical URL)."""
    existing = _existing(session, source_id, items)
    return {
        item.external_id
        for item in items
        if item.external_id in existing[0] or item.canonical_url_key in existing[1]
    }


def store_items(
    session: Session,
    source_id: int,
    language: str,
    items: list[ExtractedItem],
    *,
    now: datetime,
    baseline: bool,
) -> StoreResult:
    result = StoreResult()
    by_id, by_key = _existing(session, source_id, items)
    wilaya_ids = session.scalars(
        select(SourceWilaya.wilaya_id).where(
            SourceWilaya.source_id == source_id, SourceWilaya.enabled.is_(True)
        )
    ).all()

    for item in items:
        article = by_id.get(item.external_id) or by_key.get(item.canonical_url_key)
        if article is None:
            article = _create(session, source_id, language, item, now, baseline, wilaya_ids)
            by_id[item.external_id], by_key[item.canonical_url_key] = article, article
            if baseline:
                result.baseline += 1
            else:
                result.new.append(article.id)
        elif _update(session, article, item, now):
            result.updated += 1
        else:
            result.unchanged += 1

    for start in range(0, len(result.new), NOTIFY_MAX_IDS):
        notify(session, source_id, result.new[start : start + NOTIFY_MAX_IDS])
    return result


def notify(session: Session, source_id: int, article_ids: list[int]) -> None:
    payload = json.dumps({"source_id": source_id, "article_ids": article_ids})
    session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": NOTIFY_CHANNEL, "payload": payload},
    )


def record_run(
    session: Session,
    source_id: int,
    *,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    http_status: int | None = None,
    items_seen: int = 0,
    stored: StoreResult | None = None,
    error: str | None = None,
) -> None:
    stored = stored or StoreResult()
    session.add(
        FetchRun(
            source_id=source_id,
            started_at=started_at,
            finished_at=finished_at,
            http_status=http_status,
            items_seen=items_seen,
            items_new=len(stored.new) + stored.baseline,
            items_updated=stored.updated,
            error=error,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        )
    )
    source = session.get(Source, source_id)
    if source.status != status or source.status_changed_at is None:
        source.status_changed_at = finished_at
    source.status = status


# --- helpers -------------------------------------------------------------------------------


def _existing(session: Session, source_id: int, items: list[ExtractedItem]):
    if not items:
        return {}, {}
    rows = session.scalars(
        select(Article).where(
            Article.source_id == source_id,
            or_(
                Article.external_id.in_([i.external_id for i in items]),
                Article.canonical_url_key.in_([i.canonical_url_key for i in items]),
            ),
        )
    ).all()
    return {a.external_id: a for a in rows}, {a.canonical_url_key: a for a in rows}


def _create(session, source_id, language, item, now, baseline, wilaya_ids) -> Article:
    article = Article(
        source_id=source_id,
        external_id=item.external_id,
        url=item.url,
        canonical_url=item.url,
        canonical_url_key=item.canonical_url_key,
        title=item.title,
        lead=item.lead,
        image_url=item.image_url,
        author=item.author,
        section=item.section,
        language=language,
        published_at=item.published_at,
        published_at_confidence=item.published_at_confidence,
        modified_at=item.modified_at,
        first_seen_at=now,
        last_seen_at=now,
        content_hash=item.content_hash,
        version=1,
        baseline=baseline,
    )
    session.add(article)
    session.flush()
    session.add_all(
        ArticleWilaya(article_id=article.id, wilaya_id=w, assignment_method="source")
        for w in wilaya_ids
    )
    session.add(
        ArticleVersion(
            article_id=article.id,
            version=1,
            title=item.title,
            lead=item.lead,
            content_hash=item.content_hash,
            seen_at=now,
        )
    )
    return article


def _update(session: Session, article: Article, item: ExtractedItem, now: datetime) -> bool:
    """True when the article changed for a reader (new version)."""
    article.last_seen_at = now
    if article.published_at is None and item.published_at is not None:
        article.published_at = item.published_at
        article.published_at_confidence = item.published_at_confidence
    if item.modified_at is not None:
        article.modified_at = item.modified_at
    # values the listing doesn't carry (read from the page earlier) are kept
    lead = item.lead if item.lead is not None else article.lead
    image = item.image_url if item.image_url is not None else article.image_url
    article.section = item.section or article.section
    article.author = item.author or article.author
    digest = content_hash(item.title, lead, image)
    if digest == article.content_hash:
        return False
    article.version += 1
    article.title, article.lead, article.image_url, article.content_hash = (
        item.title,
        lead,
        image,
        digest,
    )
    session.add(
        ArticleVersion(
            article_id=article.id,
            version=article.version,
            title=item.title,
            lead=lead,
            content_hash=digest,
            seen_at=now,
        )
    )
    return True
