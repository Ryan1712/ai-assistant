"""crash_logs table

Revision ID: a0b1c2d3e4f5
Revises: 1a11430b62b9
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = '1a11430b62b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crash_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.Enum('fe_js', 'fe_api', 'fe_native_suspected', 'be_unhandled', name='crashsource'), nullable=False),
        sa.Column('severity', sa.Enum('fatal', 'error', 'warning', name='crashseverity'), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('stack', sa.Text(), nullable=True),
        sa.Column('component_stack', sa.Text(), nullable=True),
        sa.Column('screen', sa.String(length=100), nullable=True),
        sa.Column('app_version', sa.String(length=50), nullable=True),
        sa.Column('build_number', sa.String(length=50), nullable=True),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('os_version', sa.String(length=50), nullable=True),
        sa.Column('device_model', sa.String(length=100), nullable=True),
        sa.Column('is_device', sa.Boolean(), nullable=True),
        sa.Column('request_method', sa.String(length=16), nullable=True),
        sa.Column('request_path', sa.String(length=512), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('client_event_id', sa.String(length=64), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'client_event_id', name='uq_crash_log_workspace_event'),
    )
    op.create_index('ix_crash_logs_workspace_id', 'crash_logs', ['workspace_id'])
    op.create_index('ix_crash_logs_user_id', 'crash_logs', ['user_id'])
    op.create_index('ix_crash_logs_workspace_created', 'crash_logs', ['workspace_id', 'created_at'])
    op.create_index('ix_crash_logs_workspace_fingerprint', 'crash_logs', ['workspace_id', 'fingerprint'])
    op.create_index('ix_crash_logs_workspace_source', 'crash_logs', ['workspace_id', 'source'])


def downgrade() -> None:
    op.drop_index('ix_crash_logs_workspace_source', table_name='crash_logs')
    op.drop_index('ix_crash_logs_workspace_fingerprint', table_name='crash_logs')
    op.drop_index('ix_crash_logs_workspace_created', table_name='crash_logs')
    op.drop_index('ix_crash_logs_user_id', table_name='crash_logs')
    op.drop_index('ix_crash_logs_workspace_id', table_name='crash_logs')
    op.drop_table('crash_logs')
