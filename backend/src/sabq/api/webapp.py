"""Web app API (`/app/...`), behind login (docs/architecture.md#outputs). Organisation and wilaya
access is enforced here for every query, through `sabq.access.visible_articles`."""

from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import func, select

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
from sabq.auth import service
from sabq.db.models import (
    Article,
    ArticleWilaya,
    AuthToken,
    OrganisationSource,
    OrganisationWilaya,
    Source,
    SourceRequest,
    SourceWilaya,
    StoryCluster,
    StoryClusterMember,
    User,
    Wilaya,
)
from sabq.health import source_health
from sabq.matching.match import current_config

router = APIRouter(prefix="/app", tags=["web app"])
Requester = Annotated[Viewer, Depends(roles("owner", "admin", "editor"))]
TeamManager = Annotated[Viewer, Depends(roles("owner", "admin"))]
ALGIERS = ZoneInfo("Africa/Algiers")

WilayaFilter = Annotated[
    list[Annotated[str, StringConstraints(pattern=r"^\d{2}$")]] | None,
    Query(max_length=100, description="Any of these wilayas (repeat the parameter)"),
]
SourceFilter = Annotated[
    list[Annotated[str, StringConstraints(max_length=64)]] | None,
    Query(max_length=200, description="Any of these sources (repeat the parameter)"),
]
TextFilter = Annotated[str | None, Query(max_length=200, description="Words in title or lead")]


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
    state: str = Field(description="What journalists see: ok, delayed or stopped")
    state_since: datetime | None
    last_checked_at: datetime | None
    articles_per_day: float | None = Field(description="Last 14 days; null while still learning")
    edition_hour: int | None = Field(description="Algiers hour of a daily edition, if it has one")


class FacetsOut(BaseModel):
    total: int = Field(description="Articles today (Algiers time) that match the filters")
    sources: dict[str, int] = Field(description="Articles today per source slug")
    wilayas: dict[str, int] = Field(description="Articles today per wilaya code")


class MemberOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    status: str
    invited_at: datetime | None = Field(description="Latest invitation, for pending members")


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
    wilaya: WilayaFilter = None,
    source: SourceFilter = None,
    lang: Annotated[str | None, Query(max_length=8)] = None,
    since: datetime | None = None,
    q: TextFilter = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ArticlePage:
    """Newest first. Only articles of the organisation's enabled sources and wilayas."""
    query = filtered(
        viewer.organisation.id, wilayas=wilaya, sources=source, language=lang, since=since, q=q
    )
    try:
        query = page(query, cursor, limit)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from None
    rows = list(await db.scalars(query))
    items = await to_out(db, rows, organisation_id=viewer.organisation.id)
    next_cursor = encode_cursor(items[-1]) if len(items) == limit else None
    return ArticlePage(items=items, next_cursor=next_cursor)


@router.get("/articles/{article_id}")
async def article(article_id: int, viewer: LoggedIn, db: DB) -> ArticleDetail:
    found = await db.scalar(filtered(viewer.organisation.id).where(Article.id == article_id))
    if found is None:  # same answer whether it doesn't exist or isn't visible
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such article")
    return (await to_out(db, [found], detail=True, organisation_id=viewer.organisation.id))[0]


@router.get("/facets")
async def facets(
    viewer: LoggedIn,
    db: DB,
    wilaya: WilayaFilter = None,
    source: SourceFilter = None,
    q: TextFilter = None,
) -> FacetsOut:
    """Today's counts for the filter rail. `total` follows the filters, the per-source and
    per-wilaya counts don't, so the rail shows what each choice would add."""
    midnight = datetime.combine(datetime.now(ALGIERS).date(), time.min, ALGIERS).astimezone(UTC)
    today = filtered(viewer.organisation.id, since=midnight).with_only_columns(Article.id)
    matching = filtered(
        viewer.organisation.id, wilayas=wilaya, sources=source, q=q, since=midnight
    ).with_only_columns(Article.id)
    by_source = await db.execute(
        select(Source.slug, func.count())
        .join(Article, Article.source_id == Source.id)
        .where(Article.id.in_(today.scalar_subquery()))
        .group_by(Source.slug)
    )
    by_wilaya = await db.execute(
        select(Wilaya.code, func.count())
        .join(ArticleWilaya, ArticleWilaya.wilaya_id == Wilaya.id)
        .where(ArticleWilaya.article_id.in_(today.scalar_subquery()))
        .group_by(Wilaya.code)
    )
    return FacetsOut(
        total=await db.scalar(select(func.count()).select_from(matching.subquery())),
        sources=dict(by_source.all()),
        wilayas=dict(by_wilaya.all()),
    )


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
    health = {h.slug: h for h in await source_health(db, service.now())}
    return [
        SourceOut(
            slug=s.slug,
            name=s.name,
            home_url=s.home_url,
            language=s.language,
            kind=s.kind,
            status=s.status,
            wilayas=codes.get(s.id, []),
            state=health[s.slug].state,
            state_since=health[s.slug].status_since,
            last_checked_at=health[s.slug].last_checked_at,
            articles_per_day=health[s.slug].articles_per_day,
            edition_hour=health[s.slug].edition_hour,
        )
        for s in rows
    ]


@router.get("/team")
async def team(viewer: TeamManager, db: DB) -> list[MemberOut]:
    """The organisation's members and pending invitations (owner or admin)."""
    invited_at = (
        select(AuthToken.user_id, func.max(AuthToken.created_at).label("at"))
        .where(AuthToken.kind == "invite")
        .group_by(AuthToken.user_id)
        .subquery()
    )
    rows = await db.execute(
        select(User, invited_at.c.at)
        .outerjoin(invited_at, invited_at.c.user_id == User.id)
        .where(User.organisation_id == viewer.organisation.id, User.status != "disabled")
        .order_by(User.created_at, User.id)
    )
    return [
        MemberOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            invited_at=at if user.status == "invited" else None,
        )
        for user, at in rows
    ]


@router.delete(
    "/team/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(json_only)],
)
async def cancel_invitation(user_id: int, viewer: TeamManager, db: DB) -> None:
    """Cancel a pending invitation (owner or admin of the same organisation)."""
    user = await db.get(User, user_id)
    if user is None or user.organisation_id != viewer.organisation.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such member")
    if user.status != "invited":
        raise HTTPException(status.HTTP_409_CONFLICT, "only pending invitations can be cancelled")
    await db.run_sync(lambda s: service.cancel_invite(s, user, viewer.user))
    await db.commit()


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
    closed: bool = Field(description="No longer developing: its time window has passed")
    representative_id: int | None
    last_member_at: datetime | None
    articles: list[ArticleOut] = Field(description="Visible members, earliest first")


@router.get("/stories")
async def stories(
    viewer: LoggedIn,
    db: DB,
    wilaya: WilayaFilter = None,
    source: SourceFilter = None,
    q: TextFilter = None,
    state: Literal["all", "developing", "closed"] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[StoryOut]:
    """Stories (same event, several sources), newest first. Only the articles this organisation
    may see; a story with fewer than two visible articles is left out. A filter keeps the stories
    with at least one matching article, and they stay whole."""
    organisation_id = viewer.organisation.id
    visible = filtered(organisation_id).with_only_columns(Article.id).scalar_subquery()
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
    if wilaya or source or (q and q.strip()):
        matching = set(
            await db.scalars(
                filtered(organisation_id, wilayas=wilaya, sources=source, q=q).with_only_columns(
                    Article.id
                )
            )
        )
        members = {c: a for c, a in members.items() if matching & {x.id for x in a}}
    # `closed_at` is only written when a later article looks at the cluster: the window decides.
    hours = (await db.run_sync(current_config)).cluster_hours
    closed_before = service.now() - timedelta(hours=hours)
    is_closed = StoryCluster.closed_at.is_not(None) | (StoryCluster.last_member_at < closed_before)
    query = select(StoryCluster, is_closed).where(StoryCluster.id.in_(members))
    if state != "all":
        query = query.where(is_closed if state == "closed" else ~is_closed)
    clusters = (
        await db.execute(query.order_by(StoryCluster.last_member_at.desc()).limit(limit))
    ).all()
    out = []
    for cluster, closed in clusters:
        articles = sorted(members[cluster.id], key=lambda a: a.published_at or a.first_seen_at)
        out.append(
            StoryOut(
                id=cluster.id,
                status=cluster.status,
                closed=closed,
                representative_id=cluster.representative_article_id,
                last_member_at=cluster.last_member_at,
                articles=await to_out(db, articles),
            )
        )
    return out
