"""The matching step of the worker (plan M8): every `matching_tick_s`, take articles whose
embedding is pending (new ones, and ones whose title or lead changed), compute `match_text` and
`match_signals`, embed them in one batch, store the vectors and match each article in id order.

If the embeddings API fails, the articles stay `pending` and are retried on the next tick:
matching is delayed, never skipped, and ingestion never waits for it.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sabq.db.models import Article, ArticleEmbedding, Wilaya
from sabq.ingest.poller import Database
from sabq.matching.embed import Embedder, EmbeddingError, embedding_text
from sabq.matching.match import current_config, match_article
from sabq.matching.normalize import match_text
from sabq.matching.signals import Gazetteer, extract
from sabq.settings import Settings

log = logging.getLogger(__name__)


@dataclass
class TickResult:
    embedded: int = 0
    joined: int = 0
    clusters_created: int = 0
    review: int = 0
    failed: str | None = None


def pending(session: Session, limit: int) -> list[tuple[int, str, str | None]]:
    rows = session.execute(
        select(Article.id, Article.title, Article.lead)
        .where(Article.embedding_status == "pending")
        .order_by(Article.id)
        .limit(limit)
    ).all()
    return [tuple(row) for row in rows]


def store_and_match(
    session: Session, model: str, batch: list[tuple[int, str, str | None]], vectors, now: datetime
) -> TickResult:
    result = TickResult(embedded=len(batch))
    gazetteer = Gazetteer(
        [tuple(row) for row in session.execute(select(Wilaya.code, Wilaya.name_ar, Wilaya.name_fr))]
    )
    cfg = current_config(session)
    articles = []
    for (article_id, title, lead), vector in zip(batch, vectors, strict=True):
        article = session.get(Article, article_id)
        article.match_text = match_text(title, lead)
        article.match_signals = extract(title, lead, gazetteer).to_json()
        session.execute(
            delete(ArticleEmbedding).where(
                ArticleEmbedding.article_id == article_id, ArticleEmbedding.model == model
            )
        )
        session.add(ArticleEmbedding(article_id=article_id, model=model, embedding=vector))
        article.embedding_status = "done"
        articles.append(article)
    session.flush()
    for article in articles:  # in id order: later articles see the earlier ones
        outcome = match_article(session, article, model, now, cfg)
        session.flush()
        result.joined += outcome.joined is not None
        result.clusters_created += outcome.created
        result.review += outcome.review
    return result


async def tick(db: Database, embedder: Embedder, settings: Settings) -> TickResult:
    batch = await db.run(pending, settings.embedding_batch_size)
    if not batch:
        return TickResult()
    try:
        vectors = await embedder.embed([embedding_text(title, lead) for _, title, lead in batch])
    except EmbeddingError as exc:
        if not exc.retryable:  # e.g. 400 for this input: don't retry it forever
            await db.run(_mark_failed, [article_id for article_id, _, _ in batch])
        log.warning(
            "matching: %s (%d articles %s)",
            exc,
            len(batch),
            "retried later" if exc.retryable else "marked failed",
        )
        return TickResult(failed=str(exc))
    result = await db.run(store_and_match, embedder.model, batch, vectors, datetime.now(UTC))
    log.info(
        "matching: %d embedded, %d joined a story (%d new), %d for review",
        result.embedded,
        result.joined,
        result.clusters_created,
        result.review,
    )
    return result


def _mark_failed(session: Session, ids: list[int]) -> None:
    for article_id in ids:
        session.get(Article, article_id).embedding_status = "failed"


async def run(settings: Settings, db: Database, embedder: Embedder, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            result = await tick(db, embedder, settings)
            busy = result.embedded == settings.embedding_batch_size  # more waiting: go again
        except Exception:
            log.exception("matching tick failed")
            busy = False
        if not busy:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.matching_tick_s)
