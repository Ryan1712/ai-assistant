"""embeddings — Phase 6 semantic_search (spec AI upgrade 10.3)

Revision ID: e1f2a3b4c5d6
Revises: b0e866329b4c
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'b0e866329b4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('chunk_no', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', 'chunk_no',
                            name='uq_embedding_source_chunk'),
    )
    op.create_index(op.f('ix_embeddings_workspace_id'), 'embeddings', ['workspace_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_embeddings_workspace_id'), table_name='embeddings')
    op.drop_table('embeddings')
