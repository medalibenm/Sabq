"""Rename the 00 label to National/International: it also holds foreign news (2026-10-31).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename(name_ar: str, name_fr: str) -> None:
    op.execute(f"UPDATE wilayas SET name_ar = '{name_ar}', name_fr = '{name_fr}' WHERE code = '00'")


def upgrade() -> None:
    _rename("وطني/دولي", "National/International")


def downgrade() -> None:
    _rename("وطني", "National")
