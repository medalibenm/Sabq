"""Baseline articles (decision 2026-10-21): `articles.baseline`, and no detection delay for
baseline articles or articles whose only date is when we first saw them.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DELAY = "EXTRACT(EPOCH FROM (first_seen_at - published_at))"
NEW_DELAY = (
    "CASE WHEN baseline OR published_at_confidence = 'first_seen' THEN NULL "
    "ELSE EXTRACT(EPOCH FROM (first_seen_at - published_at)) END"
)


def upgrade() -> None:
    op.add_column(
        "articles", sa.Column("baseline", sa.Boolean(), server_default="false", nullable=False)
    )
    op.drop_column("articles", "detection_delay_s")
    op.add_column(
        "articles",
        sa.Column("detection_delay_s", sa.Float(), sa.Computed(NEW_DELAY, persisted=True)),
    )


def downgrade() -> None:
    op.drop_column("articles", "detection_delay_s")
    op.add_column(
        "articles",
        sa.Column("detection_delay_s", sa.Float(), sa.Computed(OLD_DELAY, persisted=True)),
    )
    op.drop_column("articles", "baseline")
