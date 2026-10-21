"""Data model (docs/architecture.md): all tables, CHECK constraints for choices.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "suspended",
                name="organisation_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')", name=op.f("ck_organisations_organisation_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organisations_slug")),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("home_url", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "official",
                "agency",
                "national",
                "local",
                "international",
                name="source_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "tier",
            sa.Enum(
                "priority",
                "normal",
                "secondary",
                name="source_tier",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("poll_interval_s", sa.Integer(), nullable=False),
        sa.Column(
            "access_method",
            sa.Enum(
                "rss",
                "wp_json",
                "sitemap",
                "embedded",
                "json_api",
                "html",
                "headless",
                name="access_method",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "egress",
            sa.Enum(
                "default",
                "dz_proxy",
                name="source_egress",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="default",
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ok",
                "degraded",
                "broken",
                "empty",
                "blocked_by_robots",
                "unreachable",
                name="source_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="ok",
            nullable=False,
        ),
        sa.Column("robots_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "access_method IN ('rss', 'wp_json', 'sitemap', 'embedded', 'json_api', 'html', 'headless')",
            name=op.f("ck_sources_access_method"),
        ),
        sa.CheckConstraint(
            "egress IN ('default', 'dz_proxy')", name=op.f("ck_sources_source_egress")
        ),
        sa.CheckConstraint(
            "kind IN ('official', 'agency', 'national', 'local', 'international')",
            name=op.f("ck_sources_source_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'degraded', 'broken', 'empty', 'blocked_by_robots', 'unreachable')",
            name=op.f("ck_sources_source_status"),
        ),
        sa.CheckConstraint(
            "tier IN ('priority', 'normal', 'secondary')", name=op.f("ck_sources_source_tier")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("slug", name=op.f("uq_sources_slug")),
    )
    op.create_table(
        "story_matching_config",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("windows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_story_matching_config")),
    )
    op.create_table(
        "wilayas",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.Column("name_ar", sa.String(length=100), nullable=False),
        sa.Column("name_fr", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("active_from", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wilayas")),
        sa.UniqueConstraint("code", name=op.f("uq_wilayas_code")),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("canonical_url_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lead", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "published_at_confidence",
            sa.Enum(
                "source_meta",
                "page_text",
                "first_seen",
                name="date_confidence",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "detection_delay_s",
            sa.Float(),
            sa.Computed("EXTRACT(EPOCH FROM (first_seen_at - published_at))", persisted=True),
            nullable=True,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("match_text", sa.Text(), nullable=True),
        sa.Column("match_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "embedding_status",
            sa.Enum(
                "pending",
                "done",
                "failed",
                name="embedding_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.CheckConstraint(
            "embedding_status IN ('pending', 'done', 'failed')",
            name=op.f("ck_articles_embedding_status"),
        ),
        sa.CheckConstraint(
            "published_at_confidence IN ('source_meta', 'page_text', 'first_seen')",
            name=op.f("ck_articles_date_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_articles_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_articles")),
        sa.UniqueConstraint(
            "source_id", "canonical_url_key", name=op.f("uq_articles_source_id_canonical_url_key")
        ),
        sa.UniqueConstraint(
            "source_id", "external_id", name=op.f("uq_articles_source_id_external_id")
        ),
    )
    op.create_index("ix_articles_first_seen_at", "articles", ["first_seen_at"], unique=False)
    op.create_index("ix_articles_published_at", "articles", ["published_at"], unique=False)
    op.create_index(
        "ix_articles_source_published", "articles", ["source_id", "published_at"], unique=False
    )
    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("items_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_new", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_fetch_runs_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fetch_runs")),
    )
    op.create_index(
        "ix_fetch_runs_source_started", "fetch_runs", ["source_id", "started_at"], unique=False
    )
    op.create_table(
        "organisation_sources",
        sa.Column("organisation_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_organisation_sources_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_organisation_sources_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organisation_id", "source_id", name=op.f("pk_organisation_sources")
        ),
    )
    op.create_table(
        "organisation_wilayas",
        sa.Column("organisation_id", sa.BigInteger(), nullable=False),
        sa.Column("wilaya_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_organisation_wilayas_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wilaya_id"],
            ["wilayas.id"],
            name=op.f("fk_organisation_wilayas_wilaya_id_wilayas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organisation_id", "wilaya_id", name=op.f("pk_organisation_wilayas")
        ),
    )
    op.create_table(
        "source_config_versions",
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_config_versions_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", "version", name=op.f("pk_source_config_versions")),
    )
    op.create_table(
        "source_wilayas",
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("wilaya_id", sa.Integer(), nullable=False),
        sa.Column(
            "assignment_method",
            sa.Enum(
                "manual",
                "source_section",
                "article_rule",
                name="source_wilaya_method",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint(
            "assignment_method IN ('manual', 'source_section', 'article_rule')",
            name=op.f("ck_source_wilayas_source_wilaya_method"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_wilayas_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wilaya_id"],
            ["wilayas.id"],
            name=op.f("fk_source_wilayas_wilaya_id_wilayas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", "wilaya_id", name=op.f("pk_source_wilayas")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("organisation_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), server_default="", nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "owner",
                "admin",
                "editor",
                "viewer",
                name="user_role",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "invited",
                "active",
                "disabled",
                name="user_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="invited",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name=op.f("ck_users_user_role")
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'disabled')", name=op.f("ck_users_user_status")
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_users_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_organisation_id"), "users", ["organisation_id"], unique=False)
    op.create_index(
        "uq_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "article_embeddings",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_article_embeddings_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("article_id", "model", name=op.f("pk_article_embeddings")),
    )
    op.create_index(
        "ix_article_embeddings_hnsw",
        "article_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "article_versions",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lead", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_article_versions_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("article_id", "version", name=op.f("pk_article_versions")),
    )
    op.create_table(
        "article_wilayas",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("wilaya_id", sa.Integer(), nullable=False),
        sa.Column(
            "assignment_method",
            sa.Enum(
                "source",
                "section",
                "entity",
                "manual",
                name="article_wilaya_method",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.CheckConstraint(
            "assignment_method IN ('source', 'section', 'entity', 'manual')",
            name=op.f("ck_article_wilayas_article_wilaya_method"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_article_wilayas_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wilaya_id"],
            ["wilayas.id"],
            name=op.f("fk_article_wilayas_wilaya_id_wilayas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("article_id", "wilaya_id", name=op.f("pk_article_wilayas")),
    )
    op.create_index(
        "ix_article_wilayas_wilaya_article",
        "article_wilayas",
        ["wilaya_id", "article_id"],
        unique=False,
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("organisation_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_audit_events_organisation_id_organisations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_org_created",
        "audit_events",
        ["organisation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "invite",
                "reset",
                name="auth_token_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('invite', 'reset')", name=op.f("ck_auth_tokens_auth_token_kind")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_tokens_token_hash")),
    )
    op.create_index(op.f("ix_auth_tokens_user_id"), "auth_tokens", ["user_id"], unique=False)
    op.create_table(
        "dedup_candidates",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "article",
                "cluster_merge",
                name="dedup_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="article",
            nullable=False,
        ),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_article_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("scorer_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "confirmed",
                "rejected",
                name="dedup_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('article', 'cluster_merge')", name=op.f("ck_dedup_candidates_dedup_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name=op.f("ck_dedup_candidates_dedup_status"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_dedup_candidates_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_article_id"],
            ["articles.id"],
            name=op.f("fk_dedup_candidates_candidate_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_dedup_candidates_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dedup_candidates")),
    )
    op.create_index(
        op.f("ix_dedup_candidates_article_id"), "dedup_candidates", ["article_id"], unique=False
    )
    op.create_index(
        op.f("ix_dedup_candidates_candidate_article_id"),
        "dedup_candidates",
        ["candidate_article_id"],
        unique=False,
    )
    op.create_index("ix_dedup_candidates_status", "dedup_candidates", ["status"], unique=False)
    op.create_table(
        "source_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("organisation_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by", sa.BigInteger(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "investigating",
                "added",
                "refused",
                name="source_request_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('new', 'investigating', 'added', 'refused')",
            name=op.f("ck_source_requests_source_request_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_source_requests_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_source_requests_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_requests")),
    )
    op.create_index(
        op.f("ix_source_requests_organisation_id"),
        "source_requests",
        ["organisation_id"],
        unique=False,
    )
    op.create_table(
        "story_clusters",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("representative_article_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "candidate",
                "automatic",
                "confirmed",
                "split",
                "rejected",
                name="cluster_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_member_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'automatic', 'confirmed', 'split', 'rejected')",
            name=op.f("ck_story_clusters_cluster_status"),
        ),
        sa.ForeignKeyConstraint(
            ["representative_article_id"],
            ["articles.id"],
            name=op.f("fk_story_clusters_representative_article_id_articles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_clusters")),
    )
    op.create_index(
        op.f("ix_story_clusters_last_member_at"), "story_clusters", ["last_member_at"], unique=False
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.create_table(
        "story_cluster_members",
        sa.Column("cluster_id", sa.BigInteger(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "membership",
            sa.Enum(
                "duplicate",
                "related",
                name="cluster_membership",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "membership IN ('duplicate', 'related')",
            name=op.f("ck_story_cluster_members_cluster_membership"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_story_cluster_members_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["story_clusters.id"],
            name=op.f("fk_story_cluster_members_cluster_id_story_clusters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cluster_id", "article_id", name=op.f("pk_story_cluster_members")),
    )
    op.create_index(
        op.f("ix_story_cluster_members_article_id"),
        "story_cluster_members",
        ["article_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_story_cluster_members_article_id"), table_name="story_cluster_members")
    op.drop_table("story_cluster_members")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index(op.f("ix_story_clusters_last_member_at"), table_name="story_clusters")
    op.drop_table("story_clusters")
    op.drop_index(op.f("ix_source_requests_organisation_id"), table_name="source_requests")
    op.drop_table("source_requests")
    op.drop_index("ix_dedup_candidates_status", table_name="dedup_candidates")
    op.drop_index(op.f("ix_dedup_candidates_candidate_article_id"), table_name="dedup_candidates")
    op.drop_index(op.f("ix_dedup_candidates_article_id"), table_name="dedup_candidates")
    op.drop_table("dedup_candidates")
    op.drop_index(op.f("ix_auth_tokens_user_id"), table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_article_wilayas_wilaya_article", table_name="article_wilayas")
    op.drop_table("article_wilayas")
    op.drop_table("article_versions")
    op.drop_index(
        "ix_article_embeddings_hnsw",
        table_name="article_embeddings",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("article_embeddings")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_index(op.f("ix_users_organisation_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("source_wilayas")
    op.drop_table("source_config_versions")
    op.drop_table("organisation_wilayas")
    op.drop_table("organisation_sources")
    op.drop_index("ix_fetch_runs_source_started", table_name="fetch_runs")
    op.drop_table("fetch_runs")
    op.drop_index("ix_articles_source_published", table_name="articles")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_first_seen_at", table_name="articles")
    op.drop_table("articles")
    op.drop_table("wilayas")
    op.drop_table("story_matching_config")
    op.drop_table("sources")
    op.drop_table("organisations")
