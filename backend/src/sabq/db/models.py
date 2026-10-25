"""SQLAlchemy models: the data model in docs/architecture.md (multi-tenant and wilaya-aware).

Enumerations are stored as text with a CHECK constraint (not PostgreSQL enum types), so adding a
value is a constraint change instead of an ALTER TYPE migration.
"""

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 1024  # voyage-4 (docs/story-matching.md)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {dict[str, Any]: JSONB, datetime: DateTime(timezone=True)}


def choice(name: str, *values: str) -> Enum:
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def fk(target: str, **kwargs: Any) -> ForeignKey:
    return ForeignKey(target, ondelete=kwargs.pop("ondelete", "CASCADE"), **kwargs)


# --- Organisations, users, sessions -------------------------------------------------------


class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        choice("organisation_status", "active", "suspended"), server_default="active"
    )
    created_at: Mapped[datetime] = created_at()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower(text("email")), unique=True),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organisation_id: Mapped[int] = mapped_column(fk("organisations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200), server_default="")
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(choice("user_role", "owner", "admin", "editor", "viewer"))
    status: Mapped[str] = mapped_column(
        choice("user_status", "invited", "active", "disabled"), server_default="invited"
    )
    # Sabq team (decision 2026-10-25): may invite into any organisation and use /admin and /api.
    # Set only from the CLI. Article access still follows the user's own organisation.
    platform_admin: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[datetime | None]


class UserSession(Base):
    __tablename__ = "user_sessions"
    # id is the SHA-256 of the session cookie token; the token itself is never stored.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(fk("users.id"), index=True)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(fk("users.id"), index=True)
    kind: Mapped[str] = mapped_column(choice("auth_token_kind", "invite", "reset"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at()


# --- Wilayas and sources -----------------------------------------------------------------


class Wilaya(Base):
    __tablename__ = "wilayas"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(2), unique=True)  # "01".."69"; "00" = National
    name_ar: Mapped[str] = mapped_column(String(100))
    name_fr: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    active_from: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at()


class OrganisationWilaya(Base):
    __tablename__ = "organisation_wilayas"
    organisation_id: Mapped[int] = mapped_column(fk("organisations.id"), primary_key=True)
    wilaya_id: Mapped[int] = mapped_column(fk("wilayas.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    home_url: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(
        choice("source_kind", "official", "agency", "national", "local", "international")
    )
    tier: Mapped[str] = mapped_column(choice("source_tier", "priority", "normal", "secondary"))
    poll_interval_s: Mapped[int] = mapped_column(Integer)
    access_method: Mapped[str] = mapped_column(
        choice(
            "access_method",
            "rss",
            "wp_json",
            "sitemap",
            "embedded",
            "json_api",
            "html",
            "headless",
        )
    )
    config: Mapped[dict[str, Any]]
    config_version: Mapped[int] = mapped_column(Integer, server_default="1")
    egress: Mapped[str] = mapped_column(
        choice("source_egress", "default", "dz_proxy"), server_default="default"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    status: Mapped[str] = mapped_column(
        choice(
            "source_status",
            "ok",
            "degraded",
            "broken",
            "empty",
            "blocked_by_robots",
            "unreachable",
        ),
        server_default="ok",
    )
    status_changed_at: Mapped[datetime | None]  # since when it has had this status (health)
    robots_checked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at()


class SourceConfigVersion(Base):
    __tablename__ = "source_config_versions"
    source_id: Mapped[int] = mapped_column(fk("sources.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    config: Mapped[dict[str, Any]]
    changed_by: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = created_at()


class SourceWilaya(Base):
    __tablename__ = "source_wilayas"
    source_id: Mapped[int] = mapped_column(fk("sources.id"), primary_key=True)
    wilaya_id: Mapped[int] = mapped_column(fk("wilayas.id"), primary_key=True)
    assignment_method: Mapped[str] = mapped_column(
        choice("source_wilaya_method", "manual", "source_section", "article_rule"),
        server_default="manual",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")


class OrganisationSource(Base):
    __tablename__ = "organisation_sources"
    organisation_id: Mapped[int] = mapped_column(fk("organisations.id"), primary_key=True)
    source_id: Mapped[int] = mapped_column(fk("sources.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")


class SourceRequest(Base):
    __tablename__ = "source_requests"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organisation_id: Mapped[int] = mapped_column(fk("organisations.id"), index=True)
    requested_by: Mapped[int | None] = mapped_column(fk("users.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(
        choice("source_request_status", "new", "investigating", "added", "refused"),
        server_default="new",
    )
    reason: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = created_at()


class FetchRun(Base):
    __tablename__ = "fetch_runs"
    __table_args__ = (Index("ix_fetch_runs_source_started", "source_id", "started_at"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(fk("sources.id"))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    http_status: Mapped[int | None] = mapped_column(Integer)
    items_seen: Mapped[int] = mapped_column(Integer, server_default="0")
    items_new: Mapped[int] = mapped_column(Integer, server_default="0")
    items_updated: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


# --- Articles ------------------------------------------------------------------------------


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        UniqueConstraint("source_id", "canonical_url_key"),
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_source_published", "source_id", "published_at"),
        Index("ix_articles_first_seen_at", "first_seen_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(fk("sources.id"))
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    canonical_url_key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    lead: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)  # internal only, never shown
    image_url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    published_at: Mapped[datetime | None]
    published_at_confidence: Mapped[str] = mapped_column(
        choice("date_confidence", "source_meta", "page_text", "first_seen")
    )
    modified_at: Mapped[datetime | None]
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Stored on a source's first poll (decision 2026-10-21): visible, never "new", no delay.
    baseline: Mapped[bool] = mapped_column(Boolean, server_default="false")
    detection_delay_s: Mapped[float | None] = mapped_column(
        Float,
        Computed(
            "CASE WHEN baseline OR published_at_confidence = 'first_seen' THEN NULL "
            "ELSE EXTRACT(EPOCH FROM (first_seen_at - published_at)) END",
            persisted=True,
        ),
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    match_text: Mapped[str | None] = mapped_column(Text)
    match_signals: Mapped[dict[str, Any] | None]
    embedding_status: Mapped[str] = mapped_column(
        choice("embedding_status", "pending", "done", "failed"), server_default="pending"
    )


class ArticleVersion(Base):
    __tablename__ = "article_versions"
    article_id: Mapped[int] = mapped_column(fk("articles.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    lead: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ArticleWilaya(Base):
    __tablename__ = "article_wilayas"
    __table_args__ = (Index("ix_article_wilayas_wilaya_article", "wilaya_id", "article_id"),)
    article_id: Mapped[int] = mapped_column(fk("articles.id"), primary_key=True)
    wilaya_id: Mapped[int] = mapped_column(fk("wilayas.id"), primary_key=True)
    assignment_method: Mapped[str] = mapped_column(
        choice("article_wilaya_method", "source", "section", "entity", "manual")
    )
    confidence: Mapped[float] = mapped_column(Float, server_default="1.0")


class ArticleEmbedding(Base):
    __tablename__ = "article_embeddings"
    __table_args__ = (
        Index(
            "ix_article_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    article_id: Mapped[int] = mapped_column(fk("articles.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String(100), primary_key=True)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = created_at()


# --- Story matching (docs/story-matching.md) ---------------------------------------------


class StoryCluster(Base):
    __tablename__ = "story_clusters"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    representative_article_id: Mapped[int | None] = mapped_column(
        fk("articles.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        choice("cluster_status", "candidate", "automatic", "confirmed", "split", "rejected")
    )
    first_published_at: Mapped[datetime | None]
    last_member_at: Mapped[datetime | None] = mapped_column(index=True)
    closed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class StoryClusterMember(Base):
    __tablename__ = "story_cluster_members"
    cluster_id: Mapped[int] = mapped_column(fk("story_clusters.id"), primary_key=True)
    article_id: Mapped[int] = mapped_column(fk("articles.id"), primary_key=True, index=True)
    membership: Mapped[str] = mapped_column(choice("cluster_membership", "duplicate", "related"))
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class StoryMatchingConfig(Base):
    __tablename__ = "story_matching_config"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    thresholds: Mapped[dict[str, Any]]
    windows: Mapped[dict[str, Any]]
    weights: Mapped[dict[str, Any]]
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at()


class DedupCandidate(Base):
    __tablename__ = "dedup_candidates"
    __table_args__ = (Index("ix_dedup_candidates_status", "status"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(
        choice("dedup_kind", "article", "cluster_merge"), server_default="article"
    )
    article_id: Mapped[int] = mapped_column(fk("articles.id"), index=True)
    candidate_article_id: Mapped[int] = mapped_column(fk("articles.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    signals: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    scorer_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        choice("dedup_status", "pending", "confirmed", "rejected"), server_default="pending"
    )
    reviewed_by: Mapped[int | None] = mapped_column(fk("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at()


# --- Audit ---------------------------------------------------------------------------------


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_org_created", "organisation_id", "created_at"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organisation_id: Mapped[int | None] = mapped_column(fk("organisations.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(fk("users.id", ondelete="SET NULL"))
    actor: Mapped[str] = mapped_column(String(200))  # user email, "cli:<os user>", "system"
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at()
