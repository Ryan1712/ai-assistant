"""public_reports_table

Revision ID: 7cdec578c242
Revises: 2fd8baf43c21
Create Date: 2026-08-12 09:26:33.537390

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cdec578c242'
down_revision: Union[str, Sequence[str], None] = '2fd8baf43c21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'public_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('draft', 'published', name='publicreportstatus'),
                  nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_public_reports_workspace_id'), 'public_reports',
                    ['workspace_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_public_reports_workspace_id'), table_name='public_reports')
    op.drop_table('public_reports')
    sa.Enum(name='publicreportstatus').drop(op.get_bind(), checkfirst=True)
