"""few_shot_examples — Phase 6 example bank (spec AI upgrade 10.4)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'few_shot_examples',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=True),
        sa.Column('user_text', sa.Text(), nullable=False),
        sa.Column('ideal_behavior', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_few_shot_examples_workspace_id'), 'few_shot_examples',
                    ['workspace_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_few_shot_examples_workspace_id'), table_name='few_shot_examples')
    op.drop_table('few_shot_examples')
