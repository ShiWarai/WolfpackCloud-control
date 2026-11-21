"""pair_codes: agent_secret for status polling

Revision ID: 005_pair_code_agent_secret
Revises: 004_drop_ros_log_entries
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa

revision = "005_pair_code_agent_secret"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pair_codes",
        sa.Column("agent_secret", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pair_codes", "agent_secret")
