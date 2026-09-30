"""Keycloak user link, networks, logical_nodes, ros logs

Revision ID: 003
Revises: 002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE workload_status AS ENUM ('pending', 'running', 'stopped', 'error')"
    )

    op.add_column("users", sa.Column("keycloak_sub", sa.String(255), nullable=True))
    op.create_index("ix_users_keycloak_sub", "users", ["keycloak_sub"], unique=True)
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.create_table(
        "networks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ros_domain_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("ros_domain_id", name="uq_networks_ros_domain_id"),
    )

    op.add_column("robots", sa.Column("network_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_robots_network_id",
        "robots",
        "networks",
        ["network_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "logical_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("network_id", sa.Integer(), nullable=True),
        sa.Column("workload_type", sa.String(length=64), nullable=False),
        sa.Column("k8s_deployment_name", sa.String(length=253), nullable=False),
        sa.Column("desired_node_hostname", sa.String(length=253), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "running",
                "stopped",
                "error",
                name="workload_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'pending'::workload_status"),
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("k8s_deployment_name", name="uq_logical_nodes_k8s_name"),
    )

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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ros_log_entries_network_id", "ros_log_entries", ["network_id"])


def downgrade() -> None:
    op.drop_index("ix_ros_log_entries_network_id", table_name="ros_log_entries")
    op.drop_table("ros_log_entries")
    op.drop_table("logical_nodes")
    op.drop_constraint("fk_robots_network_id", "robots", type_="foreignkey")
    op.drop_column("robots", "network_id")
    op.drop_table("networks")
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_index("ix_users_keycloak_sub", table_name="users")
    op.drop_column("users", "keycloak_sub")
    op.execute("DROP TYPE IF EXISTS workload_status")
