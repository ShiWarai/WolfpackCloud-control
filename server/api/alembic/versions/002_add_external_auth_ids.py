"""Add grafana_user_id and superset_user_id to users

Revision ID: 002
Revises: 001
Create Date: 2026-02-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("grafana_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("superset_user_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "superset_user_id")
    op.drop_column("users", "grafana_user_id")
