"""Source health (plan M7): `sources.status_changed_at`, how long a source has had its status.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("status_changed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("sources", "status_changed_at")
