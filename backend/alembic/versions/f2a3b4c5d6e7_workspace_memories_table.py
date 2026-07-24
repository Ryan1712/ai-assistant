"""workspace_memories — Phase 6 distiller / bộ nhớ dài hạn (spec AI upgrade 10.2)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'workspace_memories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('scope', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workspace_memories_workspace_id'), 'workspace_memories',
                    ['workspace_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_workspace_memories_workspace_id'), table_name='workspace_memories')
    op.drop_table('workspace_memories')
