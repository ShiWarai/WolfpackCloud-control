"""Drop ros_log_entries — logs moved to InfluxDB

Revision ID: 004
Revises: 003
Create Date: 2026-05-22

"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_ros_log_entries_network_id", table_name="ros_log_entries")
    op.drop_table("ros_log_entries")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "ros_log_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("network_id", sa.Integer(), nullable=True),
        sa.Column("ros_node_name", sa.String(length=512), nullable=True),
        sa.Column("level", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ros_log_entries_network_id", "ros_log_entries", ["network_id"])
