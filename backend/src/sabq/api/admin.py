"""Sabq team endpoints (platform admins only): checking sources and internal reads.

GET /admin/feeds/{slug}.xml   RSS 2.0 of a source's latest articles (lead only), to check it
GET /api/articles             internal JSON for one organisation, may include body_text
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from feedgen.feed import FeedGenerator
from sqlalchemy import select

from sabq import __version__
from sabq.api.articles import SORT_AT, ArticleDetail, filtered, page, to_out
from sabq.api.deps import DB, Viewer, platform_admin
from sabq.db.models import Article, Organisation, Source

router = APIRouter(tags=["Sabq team"])
TeamMember = Annotated[Viewer, Depends(platform_admin)]
FEED_SIZE = 50


class InternalArticle(ArticleDetail):
    body_text: str | None


@router.get("/admin/feeds/{slug}.xml", response_class=Response)
async def source_feed(slug: str, viewer: TeamMember, db: DB) -> Response:
    source = await db.scalar(select(Source).where(Source.slug == slug))
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such source")
    articles = list(
        await db.scalars(
            select(Article)
            .where(Article.source_id == source.id)
            .order_by(SORT_AT.desc(), Article.id.desc())
            .limit(FEED_SIZE)
        )
    )
    feed = FeedGenerator()
    feed.title(source.name)
    feed.link(href=source.home_url, rel="alternate")
    feed.description(f"{source.name} (Sabq check feed, {source.slug})")
    feed.language(source.language)
    feed.generator(f"Sabq {__version__}")
    for article in reversed(articles):  # feedgen prepends: add oldest first
        entry = feed.add_entry()
        entry.title(article.title)
        entry.link(href=article.url)
        entry.guid(f"{source.slug}:{article.external_id}", permalink=False)
        entry.pubDate(article.published_at or article.first_seen_at)
        if article.lead:
            entry.description(article.lead)  # lead only, never the full text
        if article.section:
            entry.category(term=article.section)
        if article.image_url:
            entry.enclosure(article.image_url, "0", "image/jpeg")
    return Response(feed.rss_str(pretty=True), media_type="application/rss+xml")


@router.get("/api/articles")
async def internal_articles(
    viewer: TeamMember,
    db: DB,
    organisation: Annotated[str, Query(description="Organisation slug (required)")],
    wilaya: Annotated[str | None, Query(pattern=r"^\d{2}$")] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    lang: Annotated[str | None, Query(max_length=8)] = None,
    since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[InternalArticle]:
    """What an organisation sees, as the Sabq team, with full text for internal use."""
    org = await db.scalar(select(Organisation).where(Organisation.slug == organisation))
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such organisation")
    query = page(
        filtered(org.id, wilaya=wilaya, source=source, language=lang, since=since), None, limit
    )
    rows = list(await db.scalars(query))
    bodies = {a.id: a.body_text for a in rows}
    return [
        InternalArticle(**item.model_dump(), body_text=bodies[item.id])
        for item in await to_out(db, rows, detail=True)
    ]
