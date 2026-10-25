"""Articles as the web app sees them: shapes, ordering, filters (shared by `/app` and the stream).

Every query starts from `sabq.access.visible_articles` (organisation, source and wilaya access).
Never `body_text`: title, lead, image, original link (CLAUDE.md, public outputs).
"""

import base64
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sabq.access import visible_articles
from sabq.db.models import Article, ArticleWilaya, Source, StoryClusterMember, Wilaya

# Newest first by publication time; articles without one by when Sabq first saw them.
SORT_AT = func.coalesce(Article.published_at, Article.first_seen_at)


class SourceRef(BaseModel):
    slug: str
    name: str
    language: str


class ArticleOut(BaseModel):
    id: int
    title: str
    lead: str | None
    image_url: str | None
    url: str
    source: SourceRef
    wilayas: list[str]
    language: str
    section: str | None
    published_at: datetime | None
    published_at_confidence: str
    first_seen_at: datetime
    sort_at: datetime
    story_cluster_id: int | None = None  # same event as other articles (M8)


class ArticleDetail(ArticleOut):
    author: str | None
    modified_at: datetime | None
    version: int


def filtered(
    organisation_id: int,
    *,
    wilaya: str | None = None,
    source: str | None = None,
    language: str | None = None,
    since: datetime | None = None,
    q: str | None = None,
) -> Select:
    query = visible_articles(organisation_id)
    if wilaya:
        query = query.where(
            exists().where(
                ArticleWilaya.article_id == Article.id,
                ArticleWilaya.wilaya_id == Wilaya.id,
                Wilaya.code == wilaya,
            )
        )
    if source:
        query = query.where(
            Article.source_id == select(Source.id).where(Source.slug == source).scalar_subquery()
        )
    if language:
        query = query.where(Article.language == language)
    if since:
        query = query.where(since <= SORT_AT)
    if q and q.strip():
        pattern = (
            "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
        query = query.where(or_(Article.title.ilike(pattern), Article.lead.ilike(pattern)))
    return query


def page(query: Select, cursor: str | None, limit: int) -> Select:
    if cursor:
        at, article_id = decode_cursor(cursor)
        query = query.where(or_(at > SORT_AT, and_(at == SORT_AT, Article.id < article_id)))
    return query.order_by(SORT_AT.desc(), Article.id.desc()).limit(limit)


def encode_cursor(item: ArticleOut) -> str:
    raw = f"{item.sort_at.isoformat()}|{item.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        at, article_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(at), int(article_id)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("invalid cursor") from None


async def to_out(db: AsyncSession, articles: list[Article], detail: bool = False) -> list:
    """Shapes for a page of articles: sources and wilayas loaded in two queries."""
    if not articles:
        return []
    ids = [a.id for a in articles]
    sources = {
        s.id: s
        for s in await db.scalars(
            select(Source).where(Source.id.in_({a.source_id for a in articles}))
        )
    }
    wilayas: dict[int, list[str]] = {}
    rows = await db.execute(
        select(ArticleWilaya.article_id, Wilaya.code)
        .join(Wilaya, Wilaya.id == ArticleWilaya.wilaya_id)
        .where(ArticleWilaya.article_id.in_(ids))
        .order_by(Wilaya.code)
    )
    for article_id, code in rows:
        wilayas.setdefault(article_id, []).append(code)
    clusters = dict(
        (
            await db.execute(
                select(StoryClusterMember.article_id, StoryClusterMember.cluster_id).where(
                    StoryClusterMember.article_id.in_(ids)
                )
            )
        ).all()
    )
    shape = ArticleDetail if detail else ArticleOut
    out = []
    for a in articles:
        source = sources[a.source_id]
        fields = {
            "id": a.id,
            "title": a.title,
            "lead": a.lead,
            "image_url": a.image_url,
            "url": a.url,
            "source": SourceRef(slug=source.slug, name=source.name, language=source.language),
            "wilayas": wilayas.get(a.id, []),
            "language": a.language,
            "section": a.section,
            "published_at": a.published_at,
            "published_at_confidence": a.published_at_confidence,
            "first_seen_at": a.first_seen_at,
            "sort_at": a.published_at or a.first_seen_at,
            "story_cluster_id": clusters.get(a.id),
        }
        if detail:
            fields |= {"author": a.author, "modified_at": a.modified_at, "version": a.version}
        out.append(shape(**fields))
    return out
