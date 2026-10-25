"""Web app API (`/app/...`), behind login (docs/architecture.md#outputs). Organisation and wilaya
access is enforced here for every query, through `sabq.access.visible_articles`."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from sabq.api.articles import (
    ArticleDetail,
    ArticleOut,
    encode_cursor,
    filtered,
    page,
    to_out,
)
from sabq.api.deps import DB, LoggedIn, Viewer, json_only, roles
from sabq.audit import record
from sabq.db.models import (
    Article,
    OrganisationSource,
    OrganisationWilaya,
    Source,
    SourceRequest,
    SourceWilaya,
    StoryCluster,
    StoryClusterMember,
    Wilaya,
)

router = APIRouter(prefix="/app", tags=["web app"])
Requester = Annotated[Viewer, Depends(roles("owner", "admin", "editor"))]


class ArticlePage(BaseModel):
    items: list[ArticleOut]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next (older) page")


class WilayaOut(BaseModel):
    code: str
    name_ar: str
    name_fr: str


class SourceOut(BaseModel):
    slug: str
    name: str
    home_url: str
    language: str
    kind: str
    status: str
    wilayas: list[str]


class SourceRequestIn(BaseModel):
    url: str = Field(max_length=2000)
    note: str = Field(default="", max_length=1000)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("must be an http(s) URL")
        return value


class SourceRequestOut(BaseModel):
    id: int
    url: str
    note: str
    status: str
    reason: str
    created_at: datetime


@router.get("/articles")
async def articles(
    viewer: LoggedIn,
    db: DB,
    wilaya: Annotated[str | None, Query(pattern=r"^\d{2}$")] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    lang: Annotated[str | None, Query(max_length=8)] = None,
    since: datetime | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Words in title or lead")] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ArticlePage:
    """Newest first. Only articles of the organisation's enabled sources and wilayas."""
    query = filtered(
        viewer.organisation.id, wilaya=wilaya, source=source, language=lang, since=since, q=q
    )
    try:
        query = page(query, cursor, limit)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from None
    items = await to_out(db, list(await db.scalars(query)))
    next_cursor = encode_cursor(items[-1]) if len(items) == limit else None
    return ArticlePage(items=items, next_cursor=next_cursor)


@router.get("/articles/{article_id}")
async def article(article_id: int, viewer: LoggedIn, db: DB) -> ArticleDetail:
    found = await db.scalar(filtered(viewer.organisation.id).where(Article.id == article_id))
    if found is None:  # same answer whether it doesn't exist or isn't visible
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such article")
    return (await to_out(db, [found], detail=True))[0]


@router.get("/wilayas")
async def wilayas(viewer: LoggedIn, db: DB) -> list[WilayaOut]:
    rows = await db.scalars(
        select(Wilaya)
        .join(OrganisationWilaya, OrganisationWilaya.wilaya_id == Wilaya.id)
        .where(
            OrganisationWilaya.organisation_id == viewer.organisation.id,
            OrganisationWilaya.enabled.is_(True),
        )
        .order_by(Wilaya.code)
    )
    return [WilayaOut(code=w.code, name_ar=w.name_ar, name_fr=w.name_fr) for w in rows]


@router.get("/sources")
async def sources(viewer: LoggedIn, db: DB) -> list[SourceOut]:
    rows = list(
        await db.scalars(
            select(Source)
            .join(OrganisationSource, OrganisationSource.source_id == Source.id)
            .where(
                OrganisationSource.organisation_id == viewer.organisation.id,
                OrganisationSource.enabled.is_(True),
                Source.enabled.is_(True),
            )
            .order_by(Source.name)
        )
    )
    codes: dict[int, list[str]] = {}
    for source_id, code in await db.execute(
        select(SourceWilaya.source_id, Wilaya.code)
        .join(Wilaya, Wilaya.id == SourceWilaya.wilaya_id)
        .where(SourceWilaya.source_id.in_([s.id for s in rows]))
        .order_by(Wilaya.code)
    ):
        codes.setdefault(source_id, []).append(code)
    return [
        SourceOut(
            slug=s.slug,
            name=s.name,
            home_url=s.home_url,
            language=s.language,
            kind=s.kind,
            status=s.status,
            wilayas=codes.get(s.id, []),
        )
        for s in rows
    ]


@router.get("/source-requests")
async def source_requests(viewer: LoggedIn, db: DB) -> list[SourceRequestOut]:
    rows = await db.scalars(
        select(SourceRequest)
        .where(SourceRequest.organisation_id == viewer.organisation.id)
        .order_by(SourceRequest.created_at.desc())
    )
    return [SourceRequestOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/source-requests",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(json_only)],
)
async def request_source(body: SourceRequestIn, viewer: Requester, db: DB) -> SourceRequestOut:
    """Ask the Sabq team to add a source (owner, admin or editor)."""
    row = SourceRequest(
        organisation_id=viewer.organisation.id,
        requested_by=viewer.user.id,
        url=body.url,
        note=body.note,
    )
    db.add(row)
    await db.flush()
    await db.run_sync(
        lambda s: record(
            s,
            f"user:{viewer.user.id}",
            "source_request.created",
            "source_request",
            row.id,
            {"url": body.url},
            organisation_id=viewer.organisation.id,
            user_id=viewer.user.id,
        )
    )
    await db.commit()
    await db.refresh(row)
    return SourceRequestOut.model_validate(row, from_attributes=True)


class StoryOut(BaseModel):
    id: int
    status: str
    last_member_at: datetime | None
    articles: list[ArticleOut] = Field(description="Visible members, earliest first")


@router.get("/stories")
async def stories(
    viewer: LoggedIn, db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[StoryOut]:
    """Stories (same event, several sources), newest first. Only the articles this organisation
    may see; a story with fewer than two visible articles is left out."""
    visible = filtered(viewer.organisation.id).with_only_columns(Article.id).scalar_subquery()
    rows = (
        await db.execute(
            select(StoryClusterMember.cluster_id, Article)
            .join(Article, Article.id == StoryClusterMember.article_id)
            .where(Article.id.in_(visible))
        )
    ).all()
    members: dict[int, list[Article]] = {}
    for cluster_id, article in rows:
        members.setdefault(cluster_id, []).append(article)
    members = {c: a for c, a in members.items() if len(a) >= 2}
    clusters = (
        await db.scalars(
            select(StoryCluster)
            .where(StoryCluster.id.in_(members))
            .order_by(StoryCluster.last_member_at.desc())
            .limit(limit)
        )
    ).all()
    out = []
    for cluster in clusters:
        articles = sorted(members[cluster.id], key=lambda a: a.published_at or a.first_seen_at)
        out.append(
            StoryOut(
                id=cluster.id,
                status=cluster.status,
                last_member_at=cluster.last_member_at,
                articles=await to_out(db, articles),
            )
        )
    return out
