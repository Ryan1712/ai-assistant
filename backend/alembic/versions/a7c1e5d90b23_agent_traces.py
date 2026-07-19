"""agent_traces — Phase 0 tracing (spec AI upgrade 4.1)

Revision ID: a7c1e5d90b23
Revises: b9e8d7c6f5a4
Create Date: 2026-07-19
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c1e5d90b23"
down_revision = "b9e8d7c6f5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("chat_request_id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=False),
        sa.Column("tools_called", sa.JSON(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["chat_request_id"], ["chat_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_traces_workspace_id"), "agent_traces",
                    ["workspace_id"])
    op.create_index(op.f("ix_agent_traces_chat_request_id"), "agent_traces",
                    ["chat_request_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_traces_chat_request_id"), table_name="agent_traces")
    op.drop_index(op.f("ix_agent_traces_workspace_id"), table_name="agent_traces")
    op.drop_table("agent_traces")
