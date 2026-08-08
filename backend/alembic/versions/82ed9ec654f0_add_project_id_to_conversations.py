"""add project_id to conversations

Revision ID: 82ed9ec654f0
Revises: ec3f35a015f9
Create Date: 2026-08-08 16:10:42.151726

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82ed9ec654f0'
down_revision: Union[str, Sequence[str], None] = 'ec3f35a015f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conversations', sa.Column('project_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('conversations_project_id_fkey', 'conversations', 'projects',
                          ['project_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('conversations_project_id_fkey', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'project_id')
