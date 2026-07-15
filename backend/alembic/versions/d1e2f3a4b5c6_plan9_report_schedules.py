"""plan9: report_schedules (bao cao dinh ky tu dong, funtional-plan 6.5)

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-07-13

Viết tay theo pattern các migration trước; schema khớp app/models.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('report_schedules',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('recipient_id', sa.Uuid(), nullable=False),
    sa.Column('weekday', sa.Integer(), nullable=True),
    sa.Column('hour', sa.Integer(), nullable=False),
    sa.Column('minute', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('assignee_id', sa.Uuid(), nullable=True),
    sa.Column('status', postgresql.ENUM('todo', 'in_progress', 'blocked', 'done',
                                        name='taskstatus', create_type=False), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_report_schedules_workspace_id'), 'report_schedules',
                    ['workspace_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_report_schedules_workspace_id'), table_name='report_schedules')
    op.drop_table('report_schedules')
